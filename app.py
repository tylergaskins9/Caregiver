from flask import Flask, jsonify, request, flash, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect, CSRFError
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please sign in to continue.'
    login_manager.login_message_category = 'info'

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

    return app
