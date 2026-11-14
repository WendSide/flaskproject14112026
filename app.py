from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from config import Config
from models import db, User, Car, Part, Favorite
from werkzeug.utils import secure_filename
import os
import uuid  # <--- ДОБАВЛЕНО для генерации уникальных имен файлов
from functools import wraps

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ==================== ДЕКОРАТОР ДЛЯ АДМИНКИ ====================
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Доступ запрещён. Требуются права администратора.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# ==================== ИНИЦИАЛИЗАЦИЯ БД И ТЕСТОВЫЕ ДАННЫЕ ====================
with app.app_context():
    db.create_all()
    
    # Гарантируем существование папки для картинок при запуске
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    if not Car.query.first():
        car1 = Car(name="ВАЗ 2114", model="2114", description="Легендарная четырнадцатая.", image="vaz2114.jpg", year=2010, price=150000)
        car2 = Car(name="ВАЗ 2114 Priora", model="2114 Priora", description="Модернизированная версия.", image="vaz2114_priora.jpg", year=2015, price=200000)
        car3 = Car(name="LADA Priora", model="Priora", description="Популярная модель.", image="priora.jpg", year=2018, price=250000)
        
        db.session.add_all([car1, car2, car3])
        db.session.commit()
        
        parts1 = [
            Part(name="Спортивный выхлоп", description="Прямоточный выхлоп", price=15000, image="exhaust.jpg", car_id=car1.id, category="Выхлопная система"),
            Part(name="Турбо кит", description="Комплект турбонаддува 0.5 бар", price=45000, image="turbo.jpg", car_id=car1.id, category="Турбонаддув"),
        ]
        db.session.add_all(parts1)
        db.session.commit()

    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', email='admin@tuningshop.ru', is_admin=True)
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()

# ==================== ОСНОВНЫЕ РОУТЫ ====================

@app.route('/')
def index():
    cars = Car.query.all()
    return render_template('index.html', cars=cars)

@app.route('/catalog')
def catalog():
    cars = Car.query.all()
    return render_template('catalog.html', cars=cars)

@app.route('/car/<int:car_id>')
def car_detail(car_id):
    car = Car.query.get_or_404(car_id)
    parts = Part.query.filter_by(car_id=car_id).all()
    return render_template('car_detail.html', car=car, parts=parts)

@app.route('/part/<int:part_id>')
def part_detail(part_id):
    part = Part.query.get_or_404(part_id)
    return render_template('part_detail.html', part=part)

@app.route('/favorites')
@login_required
def favorites():
    favorite_parts = [fav.part for fav in current_user.favorites]
    return render_template('favorites.html', parts=favorite_parts)

@app.route('/add_favorite/<int:part_id>', methods=['POST'])
@login_required
def add_favorite(part_id):
    existing = Favorite.query.filter_by(user_id=current_user.id, part_id=part_id).first()
    if not existing:
        favorite = Favorite(user_id=current_user.id, part_id=part_id)
        db.session.add(favorite)
        db.session.commit()
        flash('Добавлено в избранное!', 'success')
    return redirect(request.referrer or url_for('catalog'))

@app.route('/remove_favorite/<int:part_id>', methods=['POST'])
@login_required
def remove_favorite(part_id):
    favorite = Favorite.query.filter_by(user_id=current_user.id, part_id=part_id).first()
    if favorite:
        db.session.delete(favorite)
        db.session.commit()
        flash('Удалено из избранного', 'info')
    return redirect(request.referrer or url_for('favorites'))

@app.route('/contacts')
def contacts():
    return render_template('contacts.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember', False)
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user, remember=remember)
            next_page = request.args.get('next')
            flash('Вы успешно вошли!', 'success')
            return redirect(next_page or url_for('index'))
        else:
            flash('Неверное имя пользователя или пароль', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли из аккаунта', 'info')
    return redirect(url_for('index'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        if User.query.filter_by(username=username).first():
            flash('Пользователь с таким именем уже существует', 'error')
            return render_template('register.html')
        if User.query.filter_by(email=email).first():
            flash('Email уже зарегистрирован', 'error')
            return render_template('register.html')
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('Регистрация успешна! Теперь войдите.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/api/cars')
def api_cars():
    cars = Car.query.all()
    return jsonify([{'id': car.id, 'name': car.name, 'model': car.model, 'description': car.description, 'year': car.year, 'price': car.price} for car in cars])

@app.route('/api/parts/<int:car_id>')
def api_parts(car_id):
    parts = Part.query.filter_by(car_id=car_id).all()
    return jsonify([{'id': part.id, 'name': part.name, 'description': part.description, 'price': part.price, 'category': part.category} for part in parts])

# ==================== АДМИНКА ====================

@app.route('/admin')
@admin_required
def admin_dashboard():
    stats = {'cars': Car.query.count(), 'parts': Part.query.count(), 'users': User.query.count(), 'favorites': Favorite.query.count()}
    recent_cars = Car.query.order_by(Car.created_at.desc()).limit(5).all()
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    return render_template('admin/dashboard.html', stats=stats, recent_cars=recent_cars, recent_users=recent_users)

@app.route('/admin/cars')
@admin_required
def admin_cars():
    cars = Car.query.order_by(Car.created_at.desc()).all()
    return render_template('admin/cars.html', cars=cars)

@app.route('/admin/cars/add', methods=['GET', 'POST'])
@admin_required
def admin_add_car():
    if request.method == 'POST':
        image_file = request.files.get('image')
        image_filename = None
        if image_file and image_file.filename != '':
            # Берем расширение файла (jpg, png и т.д.)
            ext = image_file.filename.rsplit('.', 1)[1].lower() if '.' in image_file.filename else 'jpg'
            # Генерируем уникальное безопасное имя: car_уникальный_код.jpg
            image_filename = f"car_{uuid.uuid4().hex}.{ext}"
            
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))
        
        car = Car(
            name=request.form.get('name'), model=request.form.get('model'),
            description=request.form.get('description'),
            year=int(request.form.get('year')) if request.form.get('year') else None,
            price=float(request.form.get('price')) if request.form.get('price') else 0,
            image=image_filename
        )
        db.session.add(car)
        db.session.commit()
        flash('Автомобиль успешно добавлен!', 'success')
        return redirect(url_for('admin_cars'))
    return render_template('admin/car_form.html', car=None)

@app.route('/admin/cars/edit/<int:car_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_car(car_id):
    car = Car.query.get_or_404(car_id)
    if request.method == 'POST':
        car.name = request.form.get('name')
        car.model = request.form.get('model')
        car.description = request.form.get('description')
        car.year = int(request.form.get('year')) if request.form.get('year') else None
        car.price = float(request.form.get('price')) if request.form.get('price') else 0
        
        image_file = request.files.get('image')
        if image_file and image_file.filename != '':
            ext = image_file.filename.rsplit('.', 1)[1].lower() if '.' in image_file.filename else 'jpg'
            car.image = f"car_{uuid.uuid4().hex}.{ext}"
            
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], car.image))
        
        db.session.commit()
        flash('Автомобиль успешно обновлён!', 'success')
        return redirect(url_for('admin_cars'))
    return render_template('admin/car_form.html', car=car)

@app.route('/admin/cars/delete/<int:car_id>', methods=['POST'])
@admin_required
def admin_delete_car(car_id):
    car = Car.query.get_or_404(car_id)
    db.session.delete(car)
    db.session.commit()
    flash('Автомобиль удалён!', 'info')
    return redirect(url_for('admin_cars'))

@app.route('/admin/parts')
@admin_required
def admin_parts():
    parts = Part.query.order_by(Part.created_at.desc()).all()
    cars = Car.query.all()
    return render_template('admin/parts.html', parts=parts, cars=cars)

@app.route('/admin/parts/add', methods=['GET', 'POST'])
@admin_required
def admin_add_part():
    cars = Car.query.all()
    if request.method == 'POST':
        image_file = request.files.get('image')
        image_filename = None
        if image_file and image_file.filename != '':
            ext = image_file.filename.rsplit('.', 1)[1].lower() if '.' in image_file.filename else 'jpg'
            image_filename = f"part_{uuid.uuid4().hex}.{ext}"
            
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))
        
        part = Part(
            name=request.form.get('name'), description=request.form.get('description'),
            price=float(request.form.get('price')) if request.form.get('price') else 0,
            car_id=int(request.form.get('car_id')), category=request.form.get('category'),
            image=image_filename
        )
        db.session.add(part)
        db.session.commit()
        flash('Запчасть успешно добавлена!', 'success')
        return redirect(url_for('admin_parts'))
    return render_template('admin/part_form.html', part=None, cars=cars)

@app.route('/admin/parts/edit/<int:part_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_part(part_id):
    part = Part.query.get_or_404(part_id)
    cars = Car.query.all()
    if request.method == 'POST':
        part.name = request.form.get('name')
        part.description = request.form.get('description')
        part.price = float(request.form.get('price')) if request.form.get('price') else 0
        part.car_id = int(request.form.get('car_id'))
        part.category = request.form.get('category')
        
        image_file = request.files.get('image')
        if image_file and image_file.filename != '':
            ext = image_file.filename.rsplit('.', 1)[1].lower() if '.' in image_file.filename else 'jpg'
            part.image = f"part_{uuid.uuid4().hex}.{ext}"
            
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], part.image))
        
        db.session.commit()
        flash('Запчасть успешно обновлена!', 'success')
        return redirect(url_for('admin_parts'))
    return render_template('admin/part_form.html', part=part, cars=cars)

@app.route('/admin/parts/delete/<int:part_id>', methods=['POST'])
@admin_required
def admin_delete_part(part_id):
    part = Part.query.get_or_404(part_id)
    db.session.delete(part)
    db.session.commit()
    flash('Запчасть удалена!', 'info')
    return redirect(url_for('admin_parts'))

@app.route('/admin/users')
@admin_required
def admin_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users)

@app.route('/admin/users/toggle_admin/<int:user_id>', methods=['POST'])
@admin_required
def admin_toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Нельзя изменить права текущего администратора!', 'error')
    else:
        user.is_admin = not user.is_admin
        db.session.commit()
        status = 'администратором' if user.is_admin else 'обычным пользователем'
        flash(f'Пользователь {user.username} теперь {status}', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Нельзя удалить себя!', 'error')
    else:
        db.session.delete(user)
        db.session.commit()
        flash(f'Пользователь {user.username} удалён!', 'info')
    return redirect(url_for('admin_users'))

# ==================== ЗАПУСК СЕРВЕРА ====================
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)