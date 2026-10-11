"""
Seed the database with default users.
Run once: python init_db.py
"""
from run import app
from app import db
from models import User, CAREGIVER_COLORS

DEFAULTS = [
    {
        'name': 'Leigh Ann',
        'email': 'leighann@example.com',
        'role': 'admin',
        'color': CAREGIVER_COLORS[2],      # red
        'receives_full_schedule': True,
        'employment_type': 'full_time',
        'password': 'Admin@2024',
        'availability': {},
    },
]


def seed():
    with app.app_context():
        db.create_all()

        added = 0
        for d in DEFAULTS:
            if User.query.filter_by(email=d['email']).first():
                print(f'  [skip] {d["name"]} already exists')
                continue

            user = User(
                name=d['name'],
                email=d['email'],
                role=d['role'],
                color=d['color'],
                receives_full_schedule=d['receives_full_schedule'],
                employment_type=d['employment_type'],
                is_active=True,
            )
            user.set_password(d['password'])
            user.set_availability(d['availability'])
            db.session.add(user)
            added += 1
            print(f'  [+] {d["name"]}  ({d["email"]})  password: {d["password"]}')

        db.session.commit()
        print(f'\nDone. {added} user(s) added.\n')

    print('Default login credentials (change these after first login!):')
    print('  Leigh Ann  leighann@example.com   Admin@2024  [ADMIN]')
    print('  Tina       tina@example.com        Tina@2024')
    print('  Cathy      cathy@example.com       Cathy@2024')
    print('  Gamme      gamme@example.com       Gamme@2024')


if __name__ == '__main__':
    seed()
