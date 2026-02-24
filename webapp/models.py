"""
SQLAlchemy models for user authentication, management, and client data.
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


class Client(db.Model):
    """SEO/GEO client record — replaces the legacy clients.json flat file."""

    __tablename__ = 'clients'

    id = db.Column(db.String(32), primary_key=True)   # uuid hex
    name = db.Column(db.String(255), nullable=False)
    domain = db.Column(db.String(255), nullable=True, default='')
    project_name = db.Column(db.String(255), nullable=True, default='')
    cms = db.Column(db.String(100), nullable=True, default='')
    location_code = db.Column(db.Integer, nullable=True, default=2826)
    notes = db.Column(db.Text, nullable=True, default='')
    created = db.Column(db.DateTime, nullable=False,
                        default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        """Return a plain dict matching the legacy clients.json schema."""
        return {
            'id': self.id,
            'name': self.name,
            'domain': self.domain or '',
            'project_name': self.project_name or '',
            'cms': self.cms or '',
            'location_code': self.location_code or 2826,
            'notes': self.notes or '',
            'created': (
                self.created.isoformat()
                if self.created else datetime.now(timezone.utc).isoformat()
            ),
        }

    def __repr__(self) -> str:
        return f'<Client {self.name}>'
