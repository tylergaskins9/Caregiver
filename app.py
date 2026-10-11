from flask import Flask, jsonify, request, flash, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect, CSRFError
from werkzeug.middleware.proxy_fix import ProxyFix
import os
from config import Config, IS_PRODUCTION

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    if IS_PRODUCTION:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please sign in to continue.'
    login_manager.login_message_category = 'info'

    @app.context_processor
    def storage_warning():
        # Without DATABASE_URL on Render the SQLite file is wiped on every restart
        return {'data_not_persistent': IS_PRODUCTION and not os.environ.get('DATABASE_URL')}

    @login_manager.unauthorized_handler
    def unauthorized():
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Your session has expired. Please sign in again.'}), 401
        flash(login_manager.login_message, login_manager.login_message_category)
        return redirect(url_for('auth.login', next=request.full_path.rstrip('?')))

    from routes.auth import auth_bp
    from routes.main import main_bp
    from routes.api import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    csrf.exempt(api_bp)

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        if request.is_json or request.accept_mimetypes.best == 'application/json':
            return jsonify({'error': f'CSRF validation failed: {e.description}'}), 400
        flash('Your session expired. Please try again.', 'warning')
        return redirect(request.url)

    with app.app_context():
        db.create_all()
        _enable_row_level_security()
        _ensure_admin()

    return app


def _enable_row_level_security():
    # RLS with no policies blocks Supabase's public Data API; the app's owner role is unaffected
    if db.engine.dialect.name != 'postgresql':
        return
    with db.engine.begin() as conn:
        for table in db.metadata.sorted_tables:
            conn.exec_driver_sql(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY')


def _ensure_admin():
    """Create the first admin from ADMIN_EMAIL / ADMIN_PASSWORD when the database has none."""
    from models import User, CAREGIVER_COLORS

    email = os.environ.get('ADMIN_EMAIL', '').strip().lower()
    password = os.environ.get('ADMIN_PASSWORD', '')
    if not email or not password or User.query.filter_by(role='admin').first():
        return

    admin = User(
        name=os.environ.get('ADMIN_NAME', 'Leigh Ann'),
        email=email,
        role='admin',
        color=CAREGIVER_COLORS[2],
        receives_full_schedule=True,
        employment_type='full_time',
        is_active=True,
    )
    admin.set_password(password)
    admin.set_availability({})
    db.session.add(admin)
    db.session.commit()
