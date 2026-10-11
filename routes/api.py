from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from datetime import date, datetime, timedelta

import requests as http_requests

from app import db
from config import local_today
from models import User, Shift

api_bp = Blueprint('api', __name__)


def _valid_time(value):
    try:
        datetime.strptime(value, '%H:%M')
        return True
    except (TypeError, ValueError):
        return False


def _overlap_warning(shift):
    others = Shift.query.filter(
        Shift.date == shift.date,
        Shift.id != shift.id,
        Shift.start_time < shift.end_time,
        Shift.end_time > shift.start_time,
    ).all()
    if not others:
        return None
    if any(o.caregiver_id == shift.caregiver_id for o in others):
        return f'{shift.caregiver.name} is already scheduled during this time.'
    names = ', '.join(sorted({o.caregiver.name for o in others}))
    return f'This shift overlaps with {names}.'


def _event_response(shift, status=200):
    event = shift.to_event()
    warning = _overlap_warning(shift)
    if warning:
        event['warning'] = warning
    return jsonify(event), status


@api_bp.route('/events')
@login_required
def get_events():
    start_str = request.args.get('start', '')
    end_str = request.args.get('end', '')

    query = Shift.query

    if start_str:
        try:
            start_date = datetime.fromisoformat(start_str[:10]).date()
            query = query.filter(Shift.date >= start_date)
        except ValueError:
            pass

    if end_str:
        try:
            end_date = datetime.fromisoformat(end_str[:10]).date()
            query = query.filter(Shift.date <= end_date)
        except ValueError:
            pass

    if current_user.role != 'admin':
        query = query.filter(Shift.caregiver_id == current_user.id)

    shifts = query.all()
    return jsonify([s.to_event() for s in shifts])


@api_bp.route('/events', methods=['POST'])
@login_required
def create_event():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    try:
        shift_date = date.fromisoformat(data['date'])
    except (KeyError, ValueError):
        return jsonify({'error': 'Invalid or missing date'}), 400

    shift_type = data.get('shift_type', 'morning')
    if shift_type == 'morning':
        start_time, end_time = '08:00', '14:00'
    else:
        shift_type = 'evening'
        start_time, end_time = '17:00', '22:00'

    if 'start_time' in data or 'end_time' in data:
        if not (_valid_time(data.get('start_time')) and _valid_time(data.get('end_time'))):
            return jsonify({'error': 'Invalid start or end time'}), 400
        start_time, end_time = data['start_time'], data['end_time']

    caregiver_id = data.get('caregiver_id')
    if not caregiver_id:
        return jsonify({'error': 'Caregiver is required'}), 400

    caregiver = db.session.get(User, int(caregiver_id))
    if not caregiver:
        return jsonify({'error': 'Caregiver not found'}), 404

    shift = Shift(
        caregiver_id=int(caregiver_id),
        date=shift_date,
        shift_type=shift_type,
        start_time=start_time,
        end_time=end_time,
        notes=data.get('notes', ''),
    )
    db.session.add(shift)
    db.session.commit()
    return _event_response(shift, 201)


@api_bp.route('/events/<int:shift_id>', methods=['PUT'])
@login_required
def update_event(shift_id):
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    shift = db.session.get(Shift, shift_id)
    if not shift:
        return jsonify({'error': 'Shift not found'}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    if 'date' in data:
        try:
            shift.date = date.fromisoformat(data['date'])
        except ValueError:
            return jsonify({'error': 'Invalid date'}), 400

    if 'shift_type' in data:
        shift.shift_type = data['shift_type']
        if data['shift_type'] == 'morning':
            shift.start_time, shift.end_time = '08:00', '14:00'
        else:
            shift.start_time, shift.end_time = '17:00', '22:00'

    if 'start_time' in data:
        if not _valid_time(data['start_time']):
            return jsonify({'error': 'Invalid start time'}), 400
        shift.start_time = data['start_time']
    if 'end_time' in data:
        if not _valid_time(data['end_time']):
            return jsonify({'error': 'Invalid end time'}), 400
        shift.end_time = data['end_time']

    if 'caregiver_id' in data:
        caregiver = db.session.get(User, int(data['caregiver_id']))
        if caregiver:
            shift.caregiver_id = caregiver.id

    if 'notes' in data:
        shift.notes = data['notes']

    shift.updated_at = datetime.utcnow()
    db.session.commit()
    return _event_response(shift)


@api_bp.route('/events/<int:shift_id>', methods=['DELETE'])
@login_required
def delete_event(shift_id):
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    shift = db.session.get(Shift, shift_id)
    if not shift:
        return jsonify({'error': 'Shift not found'}), 404

    db.session.delete(shift)
    db.session.commit()
    return '', 204


@api_bp.route('/copy-week', methods=['POST'])
@login_required
def copy_week():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json(silent=True) or {}
    try:
        target_start = date.fromisoformat(data['week_start'])
    except (KeyError, TypeError, ValueError):
        return jsonify({'error': 'Invalid or missing week_start'}), 400

    source_start = target_start - timedelta(days=7)
    source_shifts = Shift.query.filter(
        Shift.date >= source_start,
        Shift.date < target_start,
    ).all()

    copied = skipped = 0
    for s in source_shifts:
        new_date = s.date + timedelta(days=7)
        exists = Shift.query.filter_by(
            caregiver_id=s.caregiver_id, date=new_date,
            start_time=s.start_time, end_time=s.end_time,
        ).first()
        if exists or not s.caregiver.is_active:
            skipped += 1
            continue
        db.session.add(Shift(
            caregiver_id=s.caregiver_id, date=new_date, shift_type=s.shift_type,
            start_time=s.start_time, end_time=s.end_time, notes=s.notes,
        ))
        copied += 1

    db.session.commit()
    return jsonify({'copied': copied, 'skipped': skipped})


@api_bp.route('/weekly-summary')
@login_required
def weekly_summary():
    today = local_today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    # Accept an optional week_start query param
    ws_str = request.args.get('week_start')
    if ws_str:
        try:
            week_start = date.fromisoformat(ws_str)
            week_end = week_start + timedelta(days=6)
        except ValueError:
            pass

    if current_user.role == 'admin':
        caregivers = User.query.filter_by(is_active=True, role='caregiver').order_by(User.name).all()
    else:
        caregivers = [current_user]

    summary = []
    total_hours = 0.0
    for cg in caregivers:
        hours = cg.get_weekly_hours(week_start)
        total_hours += hours
        summary.append({'name': cg.name, 'hours': round(hours, 1), 'color': cg.color})

    return jsonify({
        'week_start': week_start.isoformat(),
        'week_end': week_end.isoformat(),
        'total_hours': round(total_hours, 1),
        'target_hours': 77 if current_user.role == 'admin' else None,
        'caregivers': summary,
    })


@api_bp.route('/send-schedule', methods=['POST'])
@login_required
def send_schedule():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json(silent=True) or {}
    ws_str = data.get('week_start')

    if ws_str:
        try:
            week_start = date.fromisoformat(ws_str)
            # Normalize to Monday
            week_start = week_start - timedelta(days=week_start.weekday())
        except ValueError:
            week_start = None
    else:
        week_start = None

    if not week_start:
        today = local_today()
        week_start = today - timedelta(days=today.weekday())

    week_end = week_start + timedelta(days=6)

    caregivers = User.query.filter_by(is_active=True, role='caregiver').order_by(User.name).all()

    caregiver_schedules = []
    for cg in caregivers:
        shifts = Shift.query.filter(
            Shift.caregiver_id == cg.id,
            Shift.date >= week_start,
            Shift.date <= week_end,
        ).order_by(Shift.date, Shift.start_time).all()

        caregiver_schedules.append({
            'name': cg.name,
            'email': cg.email,
            'phone': cg.phone or '',
            'receives_full_schedule': cg.receives_full_schedule,
            'shifts': [
                {
                    'date': f"{s.date.strftime('%A, %B')} {s.date.day}",
                    'shift_type': s.shift_type.title(),
                    'time': f"{s.start_time} \u2013 {s.end_time}",
                    'notes': s.notes or '',
                }
                for s in shifts
            ],
        })

    full_schedule_recipients = [
        {'name': u.name, 'email': u.email}
        for u in User.query.filter_by(receives_full_schedule=True, is_active=True).all()
    ]

    payload = {
        'week_start': f"{week_start.strftime('%B')} {week_start.day}, {week_start.year}",
        'week_end': f"{week_end.strftime('%B')} {week_end.day}, {week_end.year}",
        'caregivers': caregiver_schedules,
        'full_schedule_recipients': full_schedule_recipients,
    }

    webhook_url = current_app.config.get('POWER_AUTOMATE_WEBHOOK_URL', '').strip()
    if not webhook_url:
        return jsonify({
            'status': 'no_webhook',
            'message': 'Power Automate webhook URL not configured.',
            'payload': payload,
        })

    try:
        resp = http_requests.post(webhook_url, json=payload, timeout=15)
        resp.raise_for_status()
        return jsonify({'status': 'success', 'message': 'Schedule sent via Power Automate.'})
    except http_requests.exceptions.RequestException as exc:
        return jsonify({'status': 'error', 'message': str(exc)}), 502
