import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # project root


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-in-prod')
    APP_PASSWORD = os.environ.get('APP_PASSWORD', '')  # empty = no auth

    DATAFORSEO_LOGIN = os.environ.get('DATAFORSEO_LOGIN', '')
    DATAFORSEO_PASSWORD = os.environ.get('DATAFORSEO_PASSWORD', '')

    AGENCY_LOGO_PATH = os.path.join(BASE_DIR, 'fonts', 'numiko_logo.png')
    FONTS_DIR = os.path.join(BASE_DIR, 'fonts')
    SCRIPTS_DIR = os.path.join(BASE_DIR, 'scripts')
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'webapp', 'uploads')
    DATA_FILE = os.path.join(BASE_DIR, 'webapp', 'data', 'clients.json')

    OUTPUT_DIR = os.environ.get('OUTPUT_DIR', '/tmp/seo-geo-reports')

    MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # 2 MB upload limit
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
