"""
Authentication & user management blueprint.

Provides login, registration (restricted to @numiko.com), email-token
activation, and an admin panel for user management.
"""
import re
import logging
from datetime import datetime, timezone
from functools import wraps
from typing import Optional

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_user, logout_user, login_required, current_user

from extensions import db, login_manager
from models import User
from config import Config
from email_service import generate_activation_token, verify_activation_token, send_activation_email

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)


# ── Flask-Login user loader ──────────────────────────────────────────────────

@login_manager.user_loader
def _load_user(user_id: str):
    return db.session.get(User, int(user_id))


@login_manager.unauthorized_handler
def _unauthorized():
    flash('Please log in to access this page.', 'error')
    return redirect(url_for('auth.login', next=request.path))


# ── Helpers ──────────────────────────────────────────────────────────────────

def admin_required(f):
    """Decorator: login_required + must be an admin."""
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _is_valid_email(email: str) -> bool:
    """Check that *email* belongs to the allowed domain."""
    domain = Config.ALLOWED_EMAIL_DOMAIN.lower()
    return bool(email) and email.lower().endswith(f'@{domain}')


_PASSWORD_RE_UPPER = re.compile(r'[A-Z]')
_PASSWORD_RE_DIGIT = re.compile(r'[0-9]')


def _validate_password(password: str) -> Optional[str]:
    """Return an error message if *password* is too weak, else ``None``."""
    if len(password) < 8:
        return 'Password must be at least 8 characters.'
    if not _PASSWORD_RE_UPPER.search(password):
        return 'Password must contain at least one uppercase letter.'
    if not _PASSWORD_RE_DIGIT.search(password):
        return 'Password must contain at least one digit.'
    return None


# ── Public routes ────────────────────────────────────────────────────────────

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        user = User.query.filter_by(email=email).first()

        if user is None or not user.check_password(password):
            flash('Invalid email or password.', 'error')
            return render_template('login.html', email=email)

        if not user.is_active:
            if user.deactivated_at:
                flash('Your account has been revoked. Contact an administrator.', 'error')
            else:
                flash('Your account has not been activated yet. Check your email for the activation link.', 'error')
            return render_template('login.html', email=email)

        login_user(user, remember=True)
        user.last_login = datetime.now(timezone.utc)
        db.session.commit()
        logger.info('User logged in: %s', user.email)

        next_page = request.args.get('next') or url_for('index')
        return redirect(next_page)

    return render_template('login.html', email='')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        error = None

        if not name:
            error = 'Name is required.'
        elif not email:
            error = 'Email is required.'
        elif not _is_valid_email(email):
            error = f'Only @{Config.ALLOWED_EMAIL_DOMAIN} email addresses are allowed.'
        elif User.query.filter_by(email=email).first():
            error = 'An account with this email already exists.'
        elif not password:
            error = 'Password is required.'
        elif password != confirm:
            error = 'Passwords do not match.'
        else:
            error = _validate_password(password)

        if error:
            flash(error, 'error')
            return render_template('register.html', name=name, email=email)

        # Create inactive user
        user = User(email=email, name=name)
        user.set_password(password)

        # Auto-promote to admin if this is the ADMIN_EMAIL
        if Config.ADMIN_EMAIL and email == Config.ADMIN_EMAIL.lower():
            user.is_admin = True

        db.session.add(user)
        db.session.commit()
        logger.info('New user registered: %s', email)

        # Generate activation token and log the URL
        token = generate_activation_token(email)
        send_activation_email(user, token)

        return render_template('register_success.html', email=email)

    return render_template('register.html', name='', email='')


@auth_bp.route('/activate/<token>')
def activate(token):
    email = verify_activation_token(token)
    if email is None:
        flash('Invalid or expired activation link.', 'error')
        return redirect(url_for('auth.login'))

    user = User.query.filter_by(email=email).first()
    if user is None:
        flash('Account not found.', 'error')
        return redirect(url_for('auth.login'))

    if user.is_active_user:
        flash('Account already activated. Please log in.', 'error')
        return redirect(url_for('auth.login'))

    user.is_active_user = True
    user.activated_at = datetime.now(timezone.utc)
    db.session.commit()
    logger.info('User activated: %s', email)

    flash('Your account has been activated! You can now log in.')
    return redirect(url_for('auth.login'))


@auth_bp.route('/logout')
@login_required
def logout():
    logger.info('User logged out: %s', current_user.email)
    logout_user()
    flash('You have been logged out.')
    return redirect(url_for('auth.login'))


# ── Admin routes ─────────────────────────────────────────────────────────────

@auth_bp.route('/admin/users')
@admin_required
def admin_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users)


@auth_bp.route('/admin/users/<int:user_id>/toggle-active', methods=['POST'])
@admin_required
def admin_toggle_active(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        flash('User not found.', 'error')
        return redirect(url_for('auth.admin_users'))

    if user.id == current_user.id:
        flash('You cannot revoke your own access.', 'error')
        return redirect(url_for('auth.admin_users'))

    if user.deactivated_at is None and user.is_active_user:
        # Revoke
        user.deactivated_at = datetime.now(timezone.utc)
        flash(f'Access revoked for {user.email}.')
        logger.info('Admin %s revoked access for %s', current_user.email, user.email)
    else:
        # Restore
        user.deactivated_at = None
        user.is_active_user = True
        if user.activated_at is None:
            user.activated_at = datetime.now(timezone.utc)
        flash(f'Access restored for {user.email}.')
        logger.info('Admin %s restored access for %s', current_user.email, user.email)

    db.session.commit()
    return redirect(url_for('auth.admin_users'))


@auth_bp.route('/admin/users/<int:user_id>/toggle-admin', methods=['POST'])
@admin_required
def admin_toggle_admin(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        flash('User not found.', 'error')
        return redirect(url_for('auth.admin_users'))

    if user.id == current_user.id:
        flash('You cannot change your own admin status.', 'error')
        return redirect(url_for('auth.admin_users'))

    user.is_admin = not user.is_admin
    db.session.commit()

    action = 'promoted to admin' if user.is_admin else 'demoted from admin'
    flash(f'{user.email} {action}.')
    logger.info('Admin %s %s %s', current_user.email, action, user.email)
    return redirect(url_for('auth.admin_users'))


@auth_bp.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        flash('User not found.', 'error')
        return redirect(url_for('auth.admin_users'))

    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('auth.admin_users'))

    email = user.email
    db.session.delete(user)
    db.session.commit()
    flash(f'User {email} deleted.')
    logger.info('Admin %s deleted user %s', current_user.email, email)
    return redirect(url_for('auth.admin_users'))
