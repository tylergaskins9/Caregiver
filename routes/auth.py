import threading
import time
from urllib.parse import urlparse

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from models import User

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60
_failed_attempts = {}
_lock = threading.Lock()


def _recent_failures(key, now):
    attempts = [t for t in _failed_attempts.get(key, []) if now - t < LOCKOUT_SECONDS]
    _failed_attempts[key] = attempts
    return attempts


def _is_locked(keys):
    now = time.time()
    with _lock:
        return any(len(_recent_failures(k, now)) >= MAX_ATTEMPTS for k in keys)


def _record_failure(keys):
    now = time.time()
    with _lock:
        for k in keys:
            _recent_failures(k, now).append(now)


def _clear_failures(keys):
    with _lock:
        for k in keys:
            _failed_attempts.pop(k, None)


def _safe_next(target):
    if not target:
        return None
    parsed = urlparse(target.replace('\\', '/'))
    if parsed.scheme or parsed.netloc or not target.startswith('/') or target.startswith('//'):
        return None
    return target


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.calendar'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = request.form.get('remember_me') == 'on'
        keys = [f'ip:{request.remote_addr}', f'email:{email}']

        if _is_locked(keys):
            flash('Too many failed sign-in attempts. Please wait 15 minutes and try again.', 'danger')
            return render_template('auth/login.html'), 429

        user = User.query.filter_by(email=email).first()
        if user and user.is_active and user.role == 'admin' and user.check_password(password):
            _clear_failures(keys)
            login_user(user, remember=remember)
            next_page = _safe_next(request.args.get('next'))
            return redirect(next_page or url_for('main.calendar'))

        _record_failure(keys)
        flash('Invalid email or password.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been signed out.', 'info')
    return redirect(url_for('auth.login'))
