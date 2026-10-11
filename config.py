import os
import secrets

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _load_secret_key():
    if os.environ.get('SECRET_KEY'):
        return os.environ['SECRET_KEY']
    key_path = os.path.join(BASE_DIR, '.secret_key')
    if not os.path.exists(key_path):
        with open(key_path, 'w') as f:
            f.write(secrets.token_hex(32))
    with open(key_path) as f:
        return f.read().strip()


def _database_uri():
    url = os.environ.get('DATABASE_URL')
    if not url:
        return 'sqlite:///' + os.path.join(BASE_DIR, 'caregiver_schedule.db')
    # SQLAlchemy requires the 'postgresql://' scheme
    return url.replace('postgres://', 'postgresql://', 1)


IS_PRODUCTION = bool(os.environ.get('RENDER'))


class Config:
    SECRET_KEY = _load_secret_key()
    MIN_PASSWORD_LENGTH = 8
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True}
    SESSION_COOKIE_SECURE = IS_PRODUCTION
    REMEMBER_COOKIE_SECURE = IS_PRODUCTION
    SESSION_COOKIE_SAMESITE = 'Lax'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    # Token stays valid for the life of the session instead of the 1-hour default
    WTF_CSRF_TIME_LIMIT = None
    # Set this to your Power Automate HTTP trigger URL to enable email sending
    POWER_AUTOMATE_WEBHOOK_URL = os.environ.get('POWER_AUTOMATE_WEBHOOK_URL', '')
