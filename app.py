import os
import uuid
from functools import wraps
from urllib.parse import urljoin, urlparse

from flask import (
    Flask,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from werkzeug.utils import secure_filename

from config import Config
from models import db, User, Car, Part, Favorite


app = Flask(__name__)
app.config.from_object(Config)

ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Сначала войдите в аккаунт."
login_manager.login_message_category = "info"


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------
# Изображения
# ---------------------------------------------------------------------

def allowed_image(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS
    )


def normalize_image_name(value):
    """
    Приводит возможные значения из БД к имени файла.

    Поддерживает:
      car.jpg
      uploads/car.jpg
      /static/uploads/car.jpg
      http://localhost:5000/static/uploads/car.jpg
    """
    if not value:
        return None

    value = str(value).strip()
    if not value:
        return None

    parsed = urlparse(value)
    path = parsed.path if parsed.scheme or parsed.netloc else value

    path = path.replace("\\", "/").lstrip("/")

    for prefix in ("static/uploads/", "uploads/", "static/images/", "images/"):
        if path.startswith(prefix):
            path = path[len(prefix):]
            break

    filename = os.path.basename(path)

    if not filename or filename in {".", ".."}:
        return None

    return filename


PLACEHOLDER_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="420">'
    '<rect width="100%" height="100%" fill="#141414" stroke="#2a2a2a"/>'
    '<text x="50%" y="50%" fill="#555" font-family="Arial, sans-serif" '
    'font-size="26" text-anchor="middle" dominant-baseline="middle">'
    '\u041d\u0435\u0442 \u0444\u043e\u0442\u043e</text>'
    '</svg>'
)


@app.route("/image/<path:filename>")
def dynamic_image(filename):
    """
    Ищет изображение: сначала в static/uploads, затем в static/images.
    Если файл не найден — возвращает SVG-заглушку (битых картинок не будет).
    """
    safe_name = os.path.basename(filename)

    search_dirs = [
        app.config["UPLOAD_FOLDER"],
        os.path.join(app.config["STATIC_DIR"], "images"),
    ]

    for folder in search_dirs:
        candidate = os.path.join(folder, safe_name)
        if os.path.isfile(candidate):
            return send_from_directory(folder, safe_name)

    # Файла нет — отдаём заглушку
    return Response(PLACEHOLDER_SVG, mimetype="image/svg+xml")


@app.route("/uploads/<path:filename>")
def uploaded_image(filename):
    """Отдаёт изображение из папки загрузок (обратная совместимость)."""
    safe_name = os.path.basename(filename)

    if safe_name != filename or not allowed_image(safe_name):
        abort(404)

    return send_from_directory(app.config["UPLOAD_FOLDER"], safe_name)


@app.template_filter("image_url")
def image_url_filter(value):
    """
    Template-фильтр: превращает значение поля image из БД
    в рабочий URL картинки.

    Использование в шаблонах:  {{ car.image|image_url }}
    """
    if value:
        value = str(value).strip()

    if not value:
        return url_for("dynamic_image", filename="no-image.png")

    # Внешние ссылки и data-URI оставляем как есть
    if value.startswith(("http://", "https://", "data:")):
        return value

    # Абсолютный путь внутри сайта (/static/..., /uploads/...)
    if value.startswith("/"):
        return value

    filename = normalize_image_name(value)
    if not filename:
        return url_for("dynamic_image", filename="no-image.png")

    return url_for("dynamic_image", filename=filename)


def save_uploaded_image(file, prefix):
    """Сохраняет загруженное изображение и возвращает имя файла."""
    if not file or not file.filename:
        return None

    original_name = secure_filename(file.filename)

    if not original_name or not allowed_image(original_name):
        raise ValueError(
            "Допустимые форматы изображений: JPG, JPEG, PNG, GIF, WEBP."
        )

    extension = original_name.rsplit(".", 1)[1].lower()
    filename = f"{prefix}_{uuid.uuid4().hex}.{extension}"

    upload_folder = app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_folder, exist_ok=True)

    file.save(os.path.join(upload_folder, filename))
    return filename


def remove_uploaded_image(filename):
    """Удаляет файл изображения, если он находится в папке загрузок."""
    safe_name = normalize_image_name(filename)
    if not safe_name:
        return

    path = os.path.join(app.config["UPLOAD_FOLDER"], safe_name)

    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        app.logger.exception("Не удалось удалить файл изображения: %s", path)


# ---------------------------------------------------------------------
# Общие функции
# ---------------------------------------------------------------------

def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("Доступ запрещён. Требуются права администратора.", "error")
            return redirect(url_for("index"))
        return view(*args, **kwargs)

    return wrapped_view


def safe_next_url(target):
    if not target:
        return None

    host_url = urlparse(request.host_url)
    target_url = urlparse(urljoin(request.host_url, target))

    if (
        target_url.scheme in {"http", "https"}
        and target_url.netloc == host_url.netloc
    ):
        return target

    return None


def commit_or_rollback():
    try:
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        app.logger.exception("Ошибка при сохранении в базе данных.")
        return False


# ---------------------------------------------------------------------
# Инициализация БД и демонстрационных данных
# ---------------------------------------------------------------------

with app.app_context():
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    db.create_all()

    if not Car.query.first():
        car1 = Car(
            name="ВАЗ 2114",
            model="2114",
            description="Легендарная четырнадцатая.",
            image="car_1bd06fefb2a343a994f9691eaf2767b4.jpg",
            year=2010,
            price=150000,
        )
        car2 = Car(
            name="ВАЗ 2114 Priora",
            model="2114 Priora",
            description="Модернизированная версия.",
            image="vaz2114_priora.jpg",
            year=2015,
            price=200000,
        )
        car3 = Car(
            name="LADA Priora",
            model="Priora",
            description="Популярная модель.",
            image="priora.jpg",
            year=2018,
            price=250000,
        )

        db.session.add_all([car1, car2, car3])

        if commit_or_rollback():
            db.session.add_all([
                Part(
                    name="Спортивный выхлоп",
                    description="Прямоточный выхлоп",
                    price=15000,
                    image="exhaust.jpg",
                    car_id=car1.id,
                    category="Выхлопная система",
                ),
                Part(
                    name="Турбо кит",
                    description="Комплект турбонаддува 0.5 бар",
                    price=45000,
                    image="turbo.jpg",
                    car_id=car1.id,
                    category="Турбонаддув",
                ),
            ])
            commit_or_rollback()

    if not User.query.filter_by(username="admin").first():
        admin = User(
            username="admin",
            email="admin@tuningshop.ru",
            is_admin=True,
        )
        admin.set_password("admin123")
        db.session.add(admin)
        commit_or_rollback()


# ---------------------------------------------------------------------
# Основные маршруты
# ---------------------------------------------------------------------

@app.route("/")
def index():
    cars = Car.query.all()
    return render_template("index.html", cars=cars)


@app.route("/catalog")
def catalog():
    cars = Car.query.all()
    return render_template("catalog.html", cars=cars)


@app.route("/car/<int:car_id>")
def car_detail(car_id):
    car = Car.query.get_or_404(car_id)
    parts = Part.query.filter_by(car_id=car.id).all()
    return render_template("car_detail.html", car=car, parts=parts)


@app.route("/part/<int:part_id>")
def part_detail(part_id):
    part = Part.query.get_or_404(part_id)
    return render_template("part_detail.html", part=part)


@app.route("/favorites")
@login_required
def favorites():
    favorite_parts = [
        favorite.part
        for favorite in current_user.favorites
        if favorite.part is not None
    ]
    return render_template("favorites.html", parts=favorite_parts)


@app.route("/add_favorite/<int:part_id>", methods=["POST"])
@login_required
def add_favorite(part_id):
    Part.query.get_or_404(part_id)

    existing = Favorite.query.filter_by(
        user_id=current_user.id,
        part_id=part_id,
    ).first()

    if not existing:
        db.session.add(Favorite(user_id=current_user.id, part_id=part_id))

        if commit_or_rollback():
            flash("Добавлено в избранное!", "success")
        else:
            flash("Не удалось добавить товар в избранное.", "error")

    return redirect(request.referrer or url_for("catalog"))


@app.route("/remove_favorite/<int:part_id>", methods=["POST"])
@login_required
def remove_favorite(part_id):
    favorite = Favorite.query.filter_by(
        user_id=current_user.id,
        part_id=part_id,
    ).first()

    if favorite:
        db.session.delete(favorite)

        if commit_or_rollback():
            flash("Удалено из избранного.", "info")
        else:
            flash("Не удалось удалить товар из избранного.", "error")

    return redirect(request.referrer or url_for("favorites"))


@app.route("/contacts")
def contacts():
    return render_template("contacts.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        remember = request.form.get("remember") in {"1", "true", "on", "yes"}

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user, remember=remember)
            flash("Вы успешно вошли!", "success")

            next_page = safe_next_url(request.args.get("next"))
            return redirect(next_page or url_for("index"))

        flash("Неверное имя пользователя или пароль.", "error")

    return render_template("login.html")


@app.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    logout_user()
    flash("Вы вышли из аккаунта.", "info")
    return redirect(url_for("index"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if not username or not email or not password:
            flash("Заполните все поля.", "error")
            return render_template("register.html")

        if len(password) < 8:
            flash("Пароль должен содержать не менее 8 символов.", "error")
            return render_template("register.html")

        if User.query.filter_by(username=username).first():
            flash("Пользователь с таким именем уже существует.", "error")
            return render_template("register.html")

        if User.query.filter_by(email=email).first():
            flash("Этот email уже зарегистрирован.", "error")
            return render_template("register.html")

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)

        if not commit_or_rollback():
            flash("Не удалось создать аккаунт. Попробуйте ещё раз.", "error")
            return render_template("register.html")

        flash("Регистрация успешна! Теперь войдите.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


# ---------------------------------------------------------------------
# API
# ---------------------------------------------------------------------

@app.route("/api/cars")
def api_cars():
    cars = Car.query.all()

    return jsonify([
        {
            "id": car.id,
            "name": car.name,
            "model": car.model,
            "description": car.description,
            "year": car.year,
            "price": float(car.price or 0),
            "image": image_url_filter(car.image),
        }
        for car in cars
    ])


@app.route("/api/parts/<int:car_id>")
def api_parts(car_id):
    Car.query.get_or_404(car_id)
    parts = Part.query.filter_by(car_id=car_id).all()

    return jsonify([
        {
            "id": part.id,
            "name": part.name,
            "description": part.description,
            "price": float(part.price or 0),
            "category": part.category,
            "image": image_url_filter(part.image),
        }
        for part in parts
    ])


# ---------------------------------------------------------------------
# Админ-панель
# ---------------------------------------------------------------------

@app.route("/admin")
@admin_required
def admin_dashboard():
    stats = {
        "cars": Car.query.count(),
        "parts": Part.query.count(),
        "users": User.query.count(),
        "favorites": Favorite.query.count(),
    }

    recent_cars = Car.query.order_by(Car.created_at.desc()).limit(5).all()
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()

    return render_template(
        "admin/dashboard.html",
        stats=stats,
        recent_cars=recent_cars,
        recent_users=recent_users,
    )


@app.route("/admin/cars")
@admin_required
def admin_cars():
    cars = Car.query.order_by(Car.created_at.desc()).all()
    return render_template("admin/cars.html", cars=cars)


@app.route("/admin/cars/add", methods=["GET", "POST"])
@admin_required
def admin_add_car():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        model = (request.form.get("model") or "").strip()

        if not name or not model:
            flash("Укажите название и модель автомобиля.", "error")
            return render_template("admin/car_form.html", car=None)

        try:
            image_filename = save_uploaded_image(
                request.files.get("image"),
                "car",
            )
        except (ValueError, RuntimeError) as error:
            flash(str(error), "error")
            return render_template("admin/car_form.html", car=None)

        try:
            year_value = (request.form.get("year") or "").strip()
            price_value = (request.form.get("price") or "").strip()

            year = int(year_value) if year_value else None
            price = float(price_value) if price_value else 0

            if price < 0:
                raise ValueError
        except ValueError:
            remove_uploaded_image(image_filename)
            flash("Проверьте корректность года и цены.", "error")
            return render_template("admin/car_form.html", car=None)

        car = Car(
            name=name,
            model=model,
            description=(request.form.get("description") or "").strip(),
            year=year,
            price=price,
            image=image_filename,
        )
        db.session.add(car)

        if not commit_or_rollback():
            remove_uploaded_image(image_filename)
            flash("Не удалось добавить автомобиль.", "error")
            return render_template("admin/car_form.html", car=None)

        flash("Автомобиль успешно добавлен!", "success")
        return redirect(url_for("admin_cars"))

    return render_template("admin/car_form.html", car=None)


@app.route("/admin/cars/edit/<int:car_id>", methods=["GET", "POST"])
@admin_required
def admin_edit_car(car_id):
    car = Car.query.get_or_404(car_id)

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        model = (request.form.get("model") or "").strip()

        if not name or not model:
            flash("Укажите название и модель автомобиля.", "error")
            return render_template("admin/car_form.html", car=car)

        try:
            year_value = (request.form.get("year") or "").strip()
            price_value = (request.form.get("price") or "").strip()

            year = int(year_value) if year_value else None
            price = float(price_value) if price_value else 0

            if price < 0:
                raise ValueError
        except ValueError:
            flash("Проверьте корректность года и цены.", "error")
            return render_template("admin/car_form.html", car=car)

        try:
            new_image = save_uploaded_image(request.files.get("image"), "car")
        except (ValueError, RuntimeError) as error:
            flash(str(error), "error")
            return render_template("admin/car_form.html", car=car)

        old_image = car.image

        car.name = name
        car.model = model
        car.description = (request.form.get("description") or "").strip()
        car.year = year
        car.price = price

        if new_image:
            car.image = new_image

        if not commit_or_rollback():
            remove_uploaded_image(new_image)
            flash("Не удалось обновить автомобиль.", "error")
            return render_template("admin/car_form.html", car=car)

        if new_image:
            remove_uploaded_image(old_image)

        flash("Автомобиль успешно обновлён!", "success")
        return redirect(url_for("admin_cars"))

    return render_template("admin/car_form.html", car=car)


@app.route("/admin/cars/delete/<int:car_id>", methods=["POST"])
@admin_required
def admin_delete_car(car_id):
    car = Car.query.get_or_404(car_id)
    parts = Part.query.filter_by(car_id=car.id).all()

    for part in parts:
        Favorite.query.filter_by(part_id=part.id).delete(
            synchronize_session=False
        )
        remove_uploaded_image(part.image)
        db.session.delete(part)

    old_image = car.image
    db.session.delete(car)

    if not commit_or_rollback():
        flash("Не удалось удалить автомобиль.", "error")
        return redirect(url_for("admin_cars"))

    remove_uploaded_image(old_image)
    flash("Автомобиль и связанные запчасти удалены.", "info")
    return redirect(url_for("admin_cars"))


@app.route("/admin/parts")
@admin_required
def admin_parts():
    parts = Part.query.order_by(Part.created_at.desc()).all()
    cars = Car.query.all()
    return render_template("admin/parts.html", parts=parts, cars=cars)


@app.route("/admin/parts/add", methods=["GET", "POST"])
@admin_required
def admin_add_part():
    cars = Car.query.all()

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        car_id_value = (request.form.get("car_id") or "").strip()

        if not name:
            flash("Укажите название запчасти.", "error")
            return render_template(
                "admin/part_form.html", part=None, cars=cars
            )

        try:
            car_id = int(car_id_value)
        except (TypeError, ValueError):
            flash("Выберите автомобиль.", "error")
            return render_template(
                "admin/part_form.html", part=None, cars=cars
            )

        car = db.session.get(Car, car_id)
        if not car:
            flash("Выбранный автомобиль не найден.", "error")
            return render_template(
                "admin/part_form.html", part=None, cars=cars
            )

        try:
            price = float(request.form.get("price") or 0)
            if price < 0:
                raise ValueError
        except ValueError:
            flash("Укажите корректную цену.", "error")
            return render_template(
                "admin/part_form.html", part=None, cars=cars
            )

        try:
            image_filename = save_uploaded_image(
                request.files.get("image"),
                "part",
            )
        except (ValueError, RuntimeError) as error:
            flash(str(error), "error")
            return render_template(
                "admin/part_form.html", part=None, cars=cars
            )

        part = Part(
            name=name,
            description=(request.form.get("description") or "").strip(),
            price=price,
            car_id=car_id,
            category=(request.form.get("category") or "").strip(),
            image=image_filename,
        )
        db.session.add(part)

        if not commit_or_rollback():
            remove_uploaded_image(image_filename)
            flash("Не удалось добавить запчасть.", "error")
            return render_template(
                "admin/part_form.html", part=None, cars=cars
            )

        flash("Запчасть успешно добавлена!", "success")
        return redirect(url_for("admin_parts"))

    return render_template("admin/part_form.html", part=None, cars=cars)


@app.route("/admin/parts/edit/<int:part_id>", methods=["GET", "POST"])
@admin_required
def admin_edit_part(part_id):
    part = Part.query.get_or_404(part_id)
    cars = Car.query.all()

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        car_id_value = (request.form.get("car_id") or "").strip()

        if not name:
            flash("Укажите название запчасти.", "error")
            return render_template(
                "admin/part_form.html", part=part, cars=cars
            )

        try:
            car_id = int(car_id_value)
            price = float(request.form.get("price") or 0)

            if price < 0:
                raise ValueError
        except (TypeError, ValueError):
            flash("Проверьте выбранный автомобиль и цену.", "error")
            return render_template(
                "admin/part_form.html", part=part, cars=cars
            )

        if not db.session.get(Car, car_id):
            flash("Выбранный автомобиль не найден.", "error")
            return render_template(
                "admin/part_form.html", part=part, cars=cars
            )

        try:
            new_image = save_uploaded_image(
                request.files.get("image"),
                "part",
            )
        except (ValueError, RuntimeError) as error:
            flash(str(error), "error")
            return render_template(
                "admin/part_form.html", part=part, cars=cars
            )

        old_image = part.image

        part.name = name
        part.description = (request.form.get("description") or "").strip()
        part.price = price
        part.car_id = car_id
        part.category = (request.form.get("category") or "").strip()

        if new_image:
            part.image = new_image

        if not commit_or_rollback():
            remove_uploaded_image(new_image)
            flash("Не удалось обновить запчасть.", "error")
            return render_template(
                "admin/part_form.html", part=part, cars=cars
            )

        if new_image:
            remove_uploaded_image(old_image)

        flash("Запчасть успешно обновлена!", "success")
        return redirect(url_for("admin_parts"))

    return render_template("admin/part_form.html", part=part, cars=cars)


@app.route("/admin/parts/delete/<int:part_id>", methods=["POST"])
@admin_required
def admin_delete_part(part_id):
    part = Part.query.get_or_404(part_id)

    Favorite.query.filter_by(part_id=part.id).delete(
        synchronize_session=False
    )

    old_image = part.image
    db.session.delete(part)

    if not commit_or_rollback():
        flash("Не удалось удалить запчасть.", "error")
        return redirect(url_for("admin_parts"))

    remove_uploaded_image(old_image)
    flash("Запчасть удалена!", "info")
    return redirect(url_for("admin_parts"))


@app.route("/admin/users")
@admin_required
def admin_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=users)


@app.route("/admin/users/toggle_admin/<int:user_id>", methods=["POST"])
@admin_required
def admin_toggle_user(user_id):
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash("Нельзя изменить права текущего администратора!", "error")
        return redirect(url_for("admin_users"))

    user.is_admin = not user.is_admin

    if commit_or_rollback():
        status = "администратором" if user.is_admin else "обычным пользователем"
        flash(f"Пользователь {user.username} теперь {status}.", "success")
    else:
        flash("Не удалось изменить права пользователя.", "error")

    return redirect(url_for("admin_users"))


@app.route("/admin/users/delete/<int:user_id>", methods=["POST"])
@admin_required
def admin_delete_user(user_id):
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash("Нельзя удалить себя!", "error")
        return redirect(url_for("admin_users"))

    username = user.username

    Favorite.query.filter_by(user_id=user.id).delete(
        synchronize_session=False
    )
    db.session.delete(user)

    if commit_or_rollback():
        flash(f"Пользователь {username} удалён!", "info")
    else:
        flash("Не удалось удалить пользователя.", "error")

    return redirect(url_for("admin_users"))



# ---------------------------------------------------------------------
# Обработка ошибок и запуск
# ---------------------------------------------------------------------

@app.errorhandler(413)
def file_too_large(_error):
    flash("Файл слишком большой. Максимальный размер — 8 МБ.", "error")
    return redirect(request.referrer or url_for("index"))


if __name__ == "__main__":
    app.run(
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
    )