"""
SQLAlchemy models for user authentication and management.
"""
from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy.orm import validates
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import db


class User(UserMixin, db.Model):
    """Registered user account."""

    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    is_active_user = db.Column(db.Boolean, default=False, nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    activated_at = db.Column(db.DateTime, nullable=True)
    last_login = db.Column(db.DateTime, nullable=True)
    deactivated_at = db.Column(db.DateTime, nullable=True)

    # ── Email normalisation ───────────────────────────────────────────────

    @validates('email')
    def _normalize_email(self, _key, value):
        """Always store emails as lowercase."""
        return value.strip().lower() if value else value

    # ── Password helpers ─────────────────────────────────────────────────

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    # ── Flask-Login integration ──────────────────────────────────────────

    @property
    def is_active(self) -> bool:
        """Account is active only when explicitly activated AND not revoked."""
        return self.is_active_user and self.deactivated_at is None

    def __repr__(self) -> str:
        return f'<User {self.email}>'
