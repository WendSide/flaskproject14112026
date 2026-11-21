from datetime import datetime
from decimal import Decimal

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash


db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(
        db.String(80),
        unique=True,
        nullable=False,
        index=True,
    )
    email = db.Column(
        db.String(120),
        unique=True,
        nullable=False,
        index=True,
    )
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    favorites = db.relationship(
        "Favorite",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def set_password(self, password):
        """Хеширует и сохраняет пароль."""
        if not password:
            raise ValueError("Пароль не может быть пустым.")
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Проверяет пароль по сохранённому хешу."""
        if not password or not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.username!r}>"


class Car(db.Model):
    __tablename__ = "cars"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, index=True)
    model = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, default="", nullable=False)
    image = db.Column(db.String(255), nullable=True)
    year = db.Column(db.Integer, nullable=True)
    price = db.Column(
        db.Numeric(12, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )

    parts = db.relationship(
        "Part",
        back_populates="car",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self):
        return f"<Car {self.name!r}>"


class Part(db.Model):
    __tablename__ = "parts"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, index=True)
    description = db.Column(db.Text, default="", nullable=False)
    price = db.Column(
        db.Numeric(12, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    image = db.Column(db.String(255), nullable=True)
    category = db.Column(db.String(100), nullable=True)

    car_id = db.Column(
        db.Integer,
        db.ForeignKey("cars.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )

    car = db.relationship("Car", back_populates="parts")
    favorites = db.relationship(
        "Favorite",
        back_populates="part",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self):
        return f"<Part {self.name!r}>"


class Favorite(db.Model):
    __tablename__ = "favorites"

    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "part_id",
            name="unique_user_part_favorite",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    part_id = db.Column(
        db.Integer,
        db.ForeignKey("parts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    user = db.relationship("User", back_populates="favorites")
    part = db.relationship("Part", back_populates="favorites")

    def __repr__(self):
        return f"<Favorite user_id={self.user_id} part_id={self.part_id}>"

        