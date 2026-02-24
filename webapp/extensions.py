"""
Shared Flask extension instances.

Importing from here (instead of creating in app.py) breaks circular imports
between app.py ↔ models.py ↔ auth.py.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()

# Redirect unauthenticated users to the login page
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'error'
