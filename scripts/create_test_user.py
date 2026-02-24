#!/usr/bin/env python3
"""One-off script to create a pre-activated test user.

Run on Railway:
    railway run python scripts/create_test_user.py

Or locally (with DATABASE_URL or SQLite):
    python scripts/create_test_user.py
"""
import os
import sys
from datetime import datetime, timezone

# Ensure webapp/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'webapp'))

from app import app
from extensions import db
from models import User

EMAIL = 'geotest@numiko.com'  # lowercase — login/register normalise to lower
NAME = 'GEO Test'
PASSWORD = 'Tk9$mPx2!vR4geo'

with app.app_context():
    # Fix any existing mixed-case version first
    mixed = User.query.filter(db.func.lower(User.email) == EMAIL).first()
    if mixed and mixed.email != EMAIL:
        print(f'Fixing email case: {mixed.email} -> {EMAIL}')
        mixed.email = EMAIL
        db.session.commit()

    existing = User.query.filter_by(email=EMAIL).first()
    if existing:
        print(f'User {EMAIL} already exists (id={existing.id}, active={existing.is_active})')
        if not existing.is_active_user:
            existing.is_active_user = True
            existing.activated_at = datetime.now(timezone.utc)
            db.session.commit()
            print('  -> Activated existing account.')
        # Reset password to known value
        existing.set_password(PASSWORD)
        db.session.commit()
        print('  -> Password reset.')
        sys.exit(0)

    user = User(
        email=EMAIL,
        name=NAME,
        is_active_user=True,
        is_admin=False,
        activated_at=datetime.now(timezone.utc),
    )
    user.set_password(PASSWORD)
    db.session.add(user)
    db.session.commit()
    print(f'Created pre-activated user: {EMAIL} (id={user.id})')
