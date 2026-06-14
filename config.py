import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'data', 'counseling.db')
SECRET_KEY = 'campus-counseling-secret-key-2024'
SESSION_COOKIE_NAME = 'cc_session'
CHECKIN_WINDOW_MINUTES_BEFORE = 15
CHECKIN_WINDOW_MINUTES_AFTER = 30
NO_SHOW_THRESHOLD = 3
COOLDOWN_DAYS = 7
