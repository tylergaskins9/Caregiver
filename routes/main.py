from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, current_app
from flask_login import login_required, current_user
from datetime import date, timedelta

from app import db
from config import local_today
from models import User, Shift, CAREGIVER_COLORS

main_bp = Blueprint('main', __name__)

DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
SHIFT_TYPES = ['morning', 'evening']


@main_bp.route('/')
@login_required
def index():
    return redirect(url_for('main.calendar'))


@main_bp.route('/calendar')
@login_required
def calendar():
    if current_user.role == 'admin':
        caregivers = User.query.filter_by(is_active=True, role='caregiver').order_by(User.name).all()
    else:
        caregivers = [current_user]
    caregiver_data = [c.to_dict() for c in caregivers]
    return render_template('calendar.html', caregivers=caregivers, caregiver_data=caregiver_data)


# ─── Caregivers ──────────────────────────────────────────────────────────────

@main_bp.route('/caregivers')
@login_required
def caregivers():
    if current_user.role != 'admin':
        abort(403)
    all_users = User.query.order_by(User.name).all()
    caregiver_data = [u.to_dict() for u in all_users]
    return render_template('caregivers.html',
                           caregivers=all_users,
                           caregiver_data=caregiver_data,
                           colors=CAREGIVER_COLORS)


@main_bp.route('/caregivers/add', methods=['POST'])
@login_required
def add_caregiver():
    if current_user.role != 'admin':
        abort(403)

    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower()

    if not name or not email:
        flash('Name and email are required.', 'danger')
        return redirect(url_for('main.caregivers'))

    if User.query.filter_by(email=email).first():
        flash('A user with that email already exists.', 'danger')
        return redirect(url_for('main.caregivers'))

    password = request.form.get('password', '').strip()
    if password and not _password_ok(password):
        return redirect(url_for('main.caregivers'))

    make_admin = 'is_admin' in request.form
    if make_admin and not password:
        flash('Set a password (at least 8 characters) for an administrator so they can sign in.', 'danger')
        return redirect(url_for('main.caregivers'))

    availability = _parse_availability(request.form)

    user = User(
        name=name,
        email=email,
        phone=request.form.get('phone', '').strip(),
        pay_rate=_safe_float(request.form.get('pay_rate')),
        employment_type=request.form.get('employment_type', 'part_time'),
        emergency_contact_name=request.form.get('emergency_contact_name', '').strip(),
        emergency_contact_phone=request.form.get('emergency_contact_phone', '').strip(),
        role='admin' if make_admin else 'caregiver',
        color=request.form.get('color', '#4e79a7'),
        receives_full_schedule='receives_full_schedule' in request.form,
        is_active=True,
    )
    user.set_availability(availability)

    if password:
        user.set_password(password)

    db.session.add(user)
    db.session.commit()
    flash(f'{name} has been added' + (' as an administrator.' if make_admin else '.'), 'success')
    return redirect(url_for('main.caregivers'))


@main_bp.route('/caregivers/<int:user_id>/edit', methods=['POST'])
@login_required
def edit_caregiver(user_id):
    if current_user.role != 'admin':
        abort(403)

    user = db.session.get(User, user_id)
    if not user:
        abort(404)

    email = request.form.get('email', '').strip().lower()
    conflict = User.query.filter_by(email=email).first()
    if conflict and conflict.id != user_id:
        flash('That email is already in use by another account.', 'danger')
        return redirect(url_for('main.caregivers'))

    password = request.form.get('password', '').strip()
    if password and not _password_ok(password):
        return redirect(url_for('main.caregivers'))

    # You can't remove your own admin access, so there is always at least one admin
    make_admin = True if user.id == current_user.id else 'is_admin' in request.form
    promoted = make_admin and user.role != 'admin'
    if promoted and not (password or user.password_hash):
        flash('Set a password (at least 8 characters) before making someone an administrator.', 'danger')
        return redirect(url_for('main.caregivers'))

    user.role = 'admin' if make_admin else 'caregiver'
    user.name = request.form.get('name', user.name).strip()
    user.email = email or user.email
    user.phone = request.form.get('phone', '').strip()
    user.pay_rate = _safe_float(request.form.get('pay_rate'))
    user.employment_type = request.form.get('employment_type', 'part_time')
    user.emergency_contact_name = request.form.get('emergency_contact_name', '').strip()
    user.emergency_contact_phone = request.form.get('emergency_contact_phone', '').strip()
    user.color = request.form.get('color', '#4e79a7')
    user.receives_full_schedule = 'receives_full_schedule' in request.form
    # The admin account can never be deactivated from the UI (would lock everyone out)
    user.is_active = True if user.role == 'admin' else 'is_active' in request.form
    user.set_availability(_parse_availability(request.form))

    if password:
        user.set_password(password)

    db.session.commit()
    if promoted:
        flash(f'{user.name} is now an administrator and can sign in. Administrators are not scheduled as caregivers.', 'success')
    else:
        flash(f'{user.name} has been updated.', 'success')
    return redirect(url_for('main.caregivers'))


@main_bp.route('/caregivers/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_caregiver(user_id):
    if current_user.role != 'admin':
        abort(403)

    user = db.session.get(User, user_id)
    if not user:
        abort(404)

    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('main.caregivers'))

    name = user.name
    db.session.delete(user)
    db.session.commit()
    flash(f'{name} has been removed.', 'success')
    return redirect(url_for('main.caregivers'))


# ─── Timesheet ───────────────────────────────────────────────────────────────

@main_bp.route('/timesheet')
@login_required
def timesheet():
    week_str = request.args.get('week')
    week_start = None
    if week_str:
        try:
            parsed = date.fromisoformat(week_str)
            week_start = parsed - timedelta(days=parsed.weekday())
        except ValueError:
            pass

    if not week_start:
        today = local_today()
        week_start = today - timedelta(days=today.weekday())

    week_end = week_start + timedelta(days=6)
    week_days = [week_start + timedelta(days=i) for i in range(7)]

    if current_user.role == 'admin':
        caregivers = User.query.filter_by(is_active=True, role='caregiver').order_by(User.name).all()
    else:
        caregivers = [current_user]

    timesheet_data = []
    total_by_day = {d: 0.0 for d in week_days}
    grand_total_hours = 0.0
    grand_total_pay = 0.0

    for cg in caregivers:
        shifts = Shift.query.filter(
            Shift.caregiver_id == cg.id,
            Shift.date >= week_start,
            Shift.date <= week_end
        ).all()

        shifts_by_day = {d: [] for d in week_days}
        for s in shifts:
            if s.date in shifts_by_day:
                shifts_by_day[s.date].append(s)
                total_by_day[s.date] += s.duration_hours

        weekly_hours = sum(s.duration_hours for s in shifts)
        weekly_pay = weekly_hours * (cg.pay_rate or 0.0)
        grand_total_hours += weekly_hours
        grand_total_pay += weekly_pay

        timesheet_data.append({
            'caregiver': cg,
            'shifts_by_day': shifts_by_day,
            'weekly_hours': weekly_hours,
            'weekly_pay': weekly_pay,
        })

    return render_template(
        'timesheet.html',
        week_start=week_start,
        week_end=week_end,
        week_days=week_days,
        timesheet_data=timesheet_data,
        total_by_day=total_by_day,
        grand_total_hours=grand_total_hours,
        grand_total_pay=grand_total_pay,
        prev_week=week_start - timedelta(days=7),
        next_week=week_start + timedelta(days=7),
        today=local_today(),
    )


# ─── Error handlers ──────────────────────────────────────────────────────────

@main_bp.app_errorhandler(403)
def forbidden(e):
    return render_template('errors/403.html'), 403


@main_bp.app_errorhandler(404)
def not_found(e):
    return render_template('errors/404.html'), 404


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _password_ok(password):
    min_len = current_app.config['MIN_PASSWORD_LENGTH']
    if len(password) < min_len:
        flash(f'Password must be at least {min_len} characters.', 'danger')
        return False
    return True


def _parse_availability(form):
    availability = {}
    for day in DAYS:
        availability[day] = {}
        for shift in SHIFT_TYPES:
            availability[day][shift] = f'avail_{day}_{shift}' in form
    return availability


def _safe_float(value, default=0.0):
    try:
        return float(value) if value else default
    except (ValueError, TypeError):
        return default
