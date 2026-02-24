import os
import logging
import stat

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # project root

# ── Constants ────────────────────────────────────────────────────────────────
DEFAULT_LOCATION_CODE = 2826  # United Kingdom
DEFAULT_CMS = 'Drupal'
DEFAULT_KEYWORD_LIMIT = 20
MAX_KEYWORD_EXPORT_LIMIT = 50


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', '')
    APP_PASSWORD = os.environ.get('APP_PASSWORD', '')  # empty = no auth

    DATAFORSEO_LOGIN = os.environ.get('DATAFORSEO_LOGIN', '')
    DATAFORSEO_PASSWORD = os.environ.get('DATAFORSEO_PASSWORD', '')

    AGENCY_LOGO_PATH = os.path.join(BASE_DIR, 'fonts', 'numiko_logo.png')
    NUMIKO_TEMPLATE_PATH = os.path.join(BASE_DIR, 'fonts', 'numiko_template.dotx')
    FONTS_DIR = os.path.join(BASE_DIR, 'fonts')
    SCRIPTS_DIR = os.path.join(BASE_DIR, 'scripts')
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'webapp', 'uploads')
    DATA_FILE = os.path.join(BASE_DIR, 'webapp', 'data', 'clients.json')

    OUTPUT_DIR = os.environ.get('OUTPUT_DIR', os.path.join(BASE_DIR, '.reports'))

    MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # 2 MB upload limit
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

    @classmethod
    def validate(cls):
        """Validate critical configuration. Call at app startup."""
        if not cls.SECRET_KEY:
            if os.environ.get('FLASK_ENV') == 'development' or os.environ.get('FLASK_DEBUG'):
                cls.SECRET_KEY = 'dev-secret-NOT-FOR-PRODUCTION'
                logger.warning('SECRET_KEY not set — using insecure dev default. '
                               'Set SECRET_KEY env var before deploying.')
            else:
                raise RuntimeError(
                    'SECRET_KEY environment variable is required in production. '
                    'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
                )

    @classmethod
    def ensure_output_dir(cls):
        """Create the report output directory with restricted permissions."""
        os.makedirs(cls.OUTPUT_DIR, exist_ok=True)
        try:
            os.chmod(cls.OUTPUT_DIR, stat.S_IRWXU)  # 700: owner only
        except OSError:
            logger.warning('Could not set permissions on OUTPUT_DIR: %s', cls.OUTPUT_DIR)
