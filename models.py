from datetime import datetime, date, timedelta
import json

from app import db, login_manager
from config import local_today
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


CAREGIVER_COLORS = [
    '#4e79a7', '#f28e2b', '#e15759', '#76b7b2',
    '#59a14f', '#edc948', '#b07aa1', '#ff9da7',
    '#9c755f', '#bab0ac',
]


class User(UserMixin, db.Model):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), default='')
    pay_rate = db.Column(db.Float, default=0.0)
    employment_type = db.Column(db.String(20), default='part_time')   # full_time | part_time
    availability = db.Column(db.Text, default='{}')                    # JSON
    emergency_contact_name = db.Column(db.String(100), default='')
    emergency_contact_phone = db.Column(db.String(20), default='')
    role = db.Column(db.String(20), default='caregiver')               # admin | caregiver
    password_hash = db.Column(db.String(256), default='')
    is_active = db.Column(db.Boolean, default=True)
    receives_full_schedule = db.Column(db.Boolean, default=False)
    color = db.Column(db.String(7), default='#4e79a7')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    shifts = db.relationship(
        'Shift', back_populates='caregiver', lazy=True, cascade='all, delete-orphan'
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    def get_availability(self):
        try:
            return json.loads(self.availability)
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_availability(self, avail_dict):
        self.availability = json.dumps(avail_dict)

    def get_weekly_hours(self, week_start=None):
        if week_start is None:
            today = local_today()
            week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        week_shifts = Shift.query.filter(
            Shift.caregiver_id == self.id,
            Shift.date >= week_start,
            Shift.date <= week_end
        ).all()
        return sum(s.duration_hours for s in week_shifts)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'phone': self.phone or '',
            'pay_rate': self.pay_rate or 0,
            'employment_type': self.employment_type or 'part_time',
            'emergency_contact_name': self.emergency_contact_name or '',
            'emergency_contact_phone': self.emergency_contact_phone or '',
            'role': self.role or 'caregiver',
            'color': self.color or '#4e79a7',
            'is_active': self.is_active,
            'receives_full_schedule': self.receives_full_schedule,
            'availability': self.get_availability(),
        }


class Shift(db.Model):
    __tablename__ = 'shift'

    id = db.Column(db.Integer, primary_key=True)
    caregiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    shift_type = db.Column(db.String(10), nullable=False)  # morning | evening
    start_time = db.Column(db.String(5), nullable=False)   # HH:MM
    end_time = db.Column(db.String(5), nullable=False)     # HH:MM
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    caregiver = db.relationship('User', back_populates='shifts')

    @property
    def duration_hours(self):
        try:
            start = datetime.strptime(self.start_time, '%H:%M')
            end = datetime.strptime(self.end_time, '%H:%M')
            return (end - start).seconds / 3600
        except ValueError:
            return 0.0

    def to_event(self):
        # Times are sent without a UTC offset so the calendar shows them exactly as saved,
        # regardless of the server's or the browser's time zone.
        def _fmt(t):
            h, m = map(int, t.split(':'))
            return f"{h % 12 or 12}{f':{m:02d}' if m else ''}{'am' if h < 12 else 'pm'}"

        label = f"{self.shift_type.title()} ({_fmt(self.start_time)}\u2013{_fmt(self.end_time)})"
        return {
            'id': self.id,
            'title': self.caregiver.name,
            'start': f"{self.date.isoformat()}T{self.start_time}:00",
            'end': f"{self.date.isoformat()}T{self.end_time}:00",
            'backgroundColor': self.caregiver.color,
            'borderColor': self.caregiver.color,
            'textColor': '#ffffff',
            'extendedProps': {
                'caregiver_id': self.caregiver_id,
                'caregiver_name': self.caregiver.name,
                'shift_type': self.shift_type,
                'shift_label': label,
                'notes': self.notes or '',
                'duration_hours': round(self.duration_hours, 1),
            }
        }
