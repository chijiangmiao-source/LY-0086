import sqlite3
import os
import hashlib
from datetime import datetime, timedelta, date
from config import DB_PATH, NO_SHOW_THRESHOLD, COOLDOWN_DAYS, ROOM_UTILIZATION_HOURS_PER_DAY

def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def _column_exists(table_name, column_name):
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in c.fetchall()]
        return column_name in columns
    finally:
        conn.close()

def _add_column_if_not_exists(table_name, column_def):
    col_name = column_def.strip().split()[0]
    if not _column_exists(table_name, col_name):
        conn = get_conn()
        c = conn.cursor()
        try:
            c.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_def}")
            conn.commit()
        finally:
            conn.close()

def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'staff',
        real_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS role_permissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role TEXT NOT NULL,
        permission TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(role, permission)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_token TEXT UNIQUE NOT NULL,
        user_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS rooms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_number TEXT UNIQUE NOT NULL,
        room_type TEXT NOT NULL,
        privacy_level TEXT NOT NULL DEFAULT 'normal',
        status TEXT NOT NULL DEFAULT 'available',
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS counselors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        title TEXT,
        specialty TEXT,
        phone TEXT,
        email TEXT,
        user_id INTEGER,
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        counselor_id INTEGER NOT NULL,
        room_id INTEGER NOT NULL,
        schedule_date DATE NOT NULL,
        start_time TIME NOT NULL,
        end_time TIME NOT NULL,
        capacity INTEGER DEFAULT 1,
        status TEXT DEFAULT 'active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (counselor_id) REFERENCES counselors(id) ON DELETE CASCADE,
        FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE CASCADE,
        UNIQUE(counselor_id, schedule_date, start_time)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS anonymous_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        anonymous_code TEXT UNIQUE NOT NULL,
        no_show_count INTEGER DEFAULT 0,
        cooldown_until DATE,
        cooldown_reason TEXT,
        last_visit_date DATE,
        risk_level TEXT DEFAULT 'low',
        risk_reason TEXT,
        risk_updated_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        appointment_no TEXT UNIQUE NOT NULL,
        anonymous_code TEXT NOT NULL,
        anonymous_user_id INTEGER,
        counselor_id INTEGER NOT NULL,
        room_id INTEGER NOT NULL,
        schedule_id INTEGER,
        appointment_date DATE NOT NULL,
        start_time TIME NOT NULL,
        end_time TIME NOT NULL,
        checkin_status TEXT DEFAULT 'pending',
        checkin_time TIMESTAMP,
        no_show_marked INTEGER DEFAULT 0,
        intervention_status TEXT DEFAULT 'none',
        is_abnormal INTEGER DEFAULT 0,
        abnormal_reason TEXT,
        reminder_sent INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (anonymous_user_id) REFERENCES anonymous_users(id),
        FOREIGN KEY (counselor_id) REFERENCES counselors(id),
        FOREIGN KEY (room_id) REFERENCES rooms(id),
        FOREIGN KEY (schedule_id) REFERENCES schedules(id) ON DELETE SET NULL
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS intervention_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        appointment_id INTEGER NOT NULL,
        anonymous_user_id INTEGER,
        anonymous_code TEXT,
        operator_id INTEGER NOT NULL,
        action_type TEXT NOT NULL,
        remark TEXT,
        old_status TEXT,
        new_status TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE CASCADE,
        FOREIGN KEY (anonymous_user_id) REFERENCES anonymous_users(id),
        FOREIGN KEY (operator_id) REFERENCES users(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS risk_warnings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        anonymous_user_id INTEGER,
        anonymous_code TEXT,
        warning_type TEXT NOT NULL,
        risk_level TEXT NOT NULL DEFAULT 'medium',
        description TEXT,
        appointment_id INTEGER,
        is_resolved INTEGER DEFAULT 0,
        resolved_by INTEGER,
        resolved_at TIMESTAMP,
        resolution_note TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (anonymous_user_id) REFERENCES anonymous_users(id),
        FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE SET NULL,
        FOREIGN KEY (resolved_by) REFERENCES users(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        notification_type TEXT NOT NULL,
        title TEXT NOT NULL,
        content TEXT,
        is_read INTEGER DEFAULT 0,
        related_appointment_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (related_appointment_id) REFERENCES appointments(id) ON DELETE SET NULL
    )''')

    conn.commit()
    conn.close()

    _add_column_if_not_exists('anonymous_users', 'risk_level TEXT DEFAULT \'low\'')
    _add_column_if_not_exists('anonymous_users', 'risk_reason TEXT')
    _add_column_if_not_exists('anonymous_users', 'risk_updated_at TIMESTAMP')
    _add_column_if_not_exists('appointments', 'is_abnormal INTEGER DEFAULT 0')
    _add_column_if_not_exists('appointments', 'abnormal_reason TEXT')
    _add_column_if_not_exists('appointments', 'reminder_sent INTEGER DEFAULT 0')
    _add_column_if_not_exists('appointments', 'schedule_id INTEGER')

    conn = get_conn()
    c = conn.cursor()

    c.execute('''CREATE INDEX IF NOT EXISTS idx_appt_date ON appointments(appointment_date)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_appt_code ON appointments(anonymous_code)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_appt_status ON appointments(checkin_status)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_sched_date ON schedules(schedule_date)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_anony_code ON anonymous_users(anonymous_code)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_risk_level ON anonymous_users(risk_level)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_warning_unresolved ON risk_warnings(is_resolved)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id, is_read)''')

    admin_pw = hashlib.sha256('admin123'.encode()).hexdigest()
    staff_pw = hashlib.sha256('staff123'.encode()).hexdigest()

    c.execute("SELECT COUNT(*) FROM users WHERE username='admin'")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO users (username, password_hash, role, real_name) VALUES (?,?,?,?)",
                  ('admin', admin_pw, 'admin', '系统管理员'))
    c.execute("SELECT COUNT(*) FROM users WHERE username='staff01'")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO users (username, password_hash, role, real_name) VALUES (?,?,?,?)",
                  ('staff01', staff_pw, 'staff', '前台工作人员'))
    c.execute("SELECT COUNT(*) FROM users WHERE username='intervention'")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO users (username, password_hash, role, real_name) VALUES (?,?,?,?)",
                  ('intervention', staff_pw, 'intervention', '干预专员'))

    default_permissions = {
        'admin': [
            'view_dashboard',
            'manage_rooms', 'manage_counselors', 'manage_schedules',
            'view_appointments', 'manage_appointments', 'check_in',
            'mark_no_show', 'cancel_appointment',
            'view_interventions', 'manage_interventions', 'lift_cooldown',
            'view_analytics', 'export_reports',
            'view_risk_warnings', 'manage_risk_warnings',
            'manage_users', 'manage_permissions',
            'view_notifications',
        ],
        'staff': [
            'view_dashboard',
            'view_rooms', 'view_counselors', 'view_schedules',
            'view_appointments', 'check_in',
            'mark_no_show', 'cancel_appointment',
            'view_interventions',
            'view_analytics',
            'view_risk_warnings',
            'view_notifications',
        ],
        'intervention': [
            'view_dashboard',
            'view_appointments',
            'view_interventions', 'manage_interventions', 'lift_cooldown',
            'view_analytics',
            'view_risk_warnings', 'manage_risk_warnings',
            'view_notifications',
        ],
        'counselor': [
            'view_dashboard',
            'view_schedules',
            'view_appointments',
            'view_notifications',
        ],
    }

    for role, perms in default_permissions.items():
        for perm in perms:
            c.execute("INSERT OR IGNORE INTO role_permissions (role, permission) VALUES (?, ?)", (role, perm))

    c.execute("SELECT COUNT(*) FROM rooms")
    if c.fetchone()[0] == 0:
        rooms_data = [
            ('R001', '个体咨询室', 'high', 'available', '一对一咨询，隔音良好'),
            ('R002', '个体咨询室', 'high', 'available', '含沙游设备'),
            ('R003', '团体辅导室', 'normal', 'available', '可容纳8-12人'),
            ('R004', '家庭咨询室', 'high', 'maintenance', '家庭治疗专用，维护中'),
            ('R005', '放松训练室', 'normal', 'available', '含生物反馈设备'),
        ]
        c.executemany("INSERT INTO rooms (room_number, room_type, privacy_level, status, description) VALUES (?,?,?,?,?)", rooms_data)

    c.execute("SELECT COUNT(*) FROM counselors")
    if c.fetchone()[0] == 0:
        counselors_data = [
            ('张明远', '高级心理咨询师', '情绪障碍、青少年心理', '13800000001', 'zhang@school.edu', 2),
            ('李心怡', '心理咨询师', '人际关系、学业压力', '13800000002', 'li@school.edu', None),
            ('王建国', '资深心理咨询师', '家庭治疗、危机干预', '13800000003', 'wang@school.edu', None),
            ('陈思雨', '心理咨询师', '焦虑抑郁、自我成长', '13800000004', 'chen@school.edu', None),
        ]
        c.executemany("INSERT INTO counselors (name, title, specialty, phone, email, user_id) VALUES (?,?,?,?,?,?)", counselors_data)

    conn.commit()
    conn.close()

def generate_appointment_no():
    now = datetime.now()
    return 'APT' + now.strftime('%Y%m%d%H%M%S') + str(now.microsecond // 1000).zfill(3)

def check_time_overlap(start1, end1, start2, end2):
    from datetime import datetime
    fmt = '%H:%M'
    s1 = datetime.strptime(start1, fmt)
    e1 = datetime.strptime(end1, fmt)
    s2 = datetime.strptime(start2, fmt)
    e2 = datetime.strptime(end2, fmt)
    return s1 < e2 and s2 < e1

def get_anonymous_user(anonymous_code):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM anonymous_users WHERE anonymous_code = ?", (anonymous_code,))
    row = c.fetchone()
    user = dict(row) if row else None
    conn.close()
    return user

def create_or_get_anonymous_user(anonymous_code):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM anonymous_users WHERE anonymous_code = ?", (anonymous_code,))
    row = c.fetchone()
    if row:
        au = dict(row)
    else:
        c.execute("INSERT INTO anonymous_users (anonymous_code) VALUES (?)", (anonymous_code,))
        conn.commit()
        c.execute("SELECT * FROM anonymous_users WHERE id = ?", (c.lastrowid,))
        au = dict(c.fetchone())
    conn.close()
    return au

def is_in_cooldown(anonymous_code, target_date=None):
    if target_date is None:
        target_date = datetime.now().date()
    au = get_anonymous_user(anonymous_code)
    if not au or not au.get('cooldown_until'):
        return False, None
    cooldown_date = datetime.strptime(au['cooldown_until'], '%Y-%m-%d').date()
    if target_date <= cooldown_date:
        return True, au['cooldown_until']
    return False, None

def check_concurrent_appointment(anonymous_code, appointment_date, start_time, end_time, exclude_id=None):
    conn = get_conn()
    c = conn.cursor()
    query = """SELECT a.*, r.room_number, cou.name as counselor_name 
               FROM appointments a 
               JOIN rooms r ON a.room_id = r.id
               JOIN counselors cou ON a.counselor_id = cou.id
               WHERE a.anonymous_code = ? 
               AND a.appointment_date = ? 
               AND a.checkin_status != 'cancelled'
               AND a.no_show_marked = 0"""
    params = [anonymous_code, appointment_date]
    if exclude_id:
        query += " AND a.id != ?"
        params.append(exclude_id)
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    for row in rows:
        if check_time_overlap(start_time, end_time, row['start_time'], row['end_time']):
            return dict(row)
    return None

def increment_no_show(anonymous_user_id, anonymous_code):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM anonymous_users WHERE id = ?", (anonymous_user_id,))
    au = c.fetchone()
    new_count = (au['no_show_count'] if au else 0) + 1
    cooldown_until = None
    reason = None
    if new_count >= NO_SHOW_THRESHOLD:
        cooldown_until = (datetime.now() + timedelta(days=COOLDOWN_DAYS)).strftime('%Y-%m-%d')
        reason = f'连续失约{new_count}次，自动触发{COOLDOWN_DAYS}天冷静期'
    c.execute("UPDATE anonymous_users SET no_show_count = ?, cooldown_until = ?, cooldown_reason = ? WHERE id = ?",
              (new_count, cooldown_until, reason, anonymous_user_id))
    conn.commit()
    conn.close()
    return cooldown_until, reason, new_count

def reset_consecutive_no_show(anonymous_user_id, reason='正常履约'):
    if not anonymous_user_id:
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE anonymous_users SET no_show_count = 0 WHERE id = ? AND no_show_count > 0", (anonymous_user_id,))
    conn.commit()
    conn.close()

def check_schedule_counselor_conflict(counselor_id, schedule_date, start_time, end_time, exclude_schedule_id=None):
    conn = get_conn()
    c = conn.cursor()
    query = """SELECT * FROM schedules WHERE counselor_id = ? AND schedule_date = ? AND status = 'active'"""
    params = [counselor_id, schedule_date]
    if exclude_schedule_id:
        query += " AND id != ?"
        params.append(exclude_schedule_id)
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    for row in rows:
        if check_time_overlap(start_time, end_time, row['start_time'], row['end_time']):
            return dict(row)
    return None

def check_schedule_room_conflict(room_id, schedule_date, start_time, end_time, exclude_schedule_id=None):
    conn = get_conn()
    c = conn.cursor()
    query = """SELECT s.*, cou.name as counselor_name FROM schedules s
               JOIN counselors cou ON s.counselor_id = cou.id
               WHERE s.room_id = ? AND s.schedule_date = ? AND s.status = 'active'"""
    params = [room_id, schedule_date]
    if exclude_schedule_id:
        query += " AND s.id != ?"
        params.append(exclude_schedule_id)
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    for row in rows:
        if check_time_overlap(start_time, end_time, row['start_time'], row['end_time']):
            return dict(row)
    return None

def check_schedule_capacity(schedule_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT s.capacity,
                        (SELECT COUNT(*) FROM appointments a
                         WHERE a.schedule_id = s.id
                         AND a.checkin_status != 'cancelled'
                         AND a.no_show_marked = 0) as booked
                 FROM schedules s WHERE s.id = ?""", (schedule_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    booked = row['booked']
    capacity = row['capacity'] or 1
    return {
        'booked': booked,
        'capacity': capacity,
        'available': max(0, capacity - booked),
        'full': booked >= capacity,
    }

def check_schedule_capacity_with_lock(schedule_id, conn):
    c = conn.cursor()
    c.execute("""SELECT s.capacity,
                        (SELECT COUNT(*) FROM appointments a
                         WHERE a.schedule_id = s.id
                         AND a.checkin_status != 'cancelled'
                         AND a.no_show_marked = 0) as booked
                 FROM schedules s WHERE s.id = ?""", (schedule_id,))
    row = c.fetchone()
    if not row:
        return None
    booked = row['booked']
    capacity = row['capacity'] or 1
    return {
        'booked': booked,
        'capacity': capacity,
        'available': max(0, capacity - booked),
        'full': booked >= capacity,
    }

def check_appointment_counselor_conflict(counselor_id, appointment_date, start_time, end_time, exclude_appointment_id=None):
    conn = get_conn()
    c = conn.cursor()
    query = """SELECT a.*, r.room_number
               FROM appointments a
               JOIN rooms r ON a.room_id = r.id
               WHERE a.counselor_id = ?
               AND a.appointment_date = ?
               AND a.checkin_status != 'cancelled'
               AND a.no_show_marked = 0"""
    params = [counselor_id, appointment_date]
    if exclude_appointment_id:
        query += " AND a.id != ?"
        params.append(exclude_appointment_id)
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    for row in rows:
        if check_time_overlap(start_time, end_time, row['start_time'], row['end_time']):
            return dict(row)
    return None

def check_appointment_room_conflict(room_id, appointment_date, start_time, end_time, exclude_appointment_id=None):
    conn = get_conn()
    c = conn.cursor()
    query = """SELECT a.*, cou.name as counselor_name
               FROM appointments a
               JOIN counselors cou ON a.counselor_id = cou.id
               WHERE a.room_id = ?
               AND a.appointment_date = ?
               AND a.checkin_status != 'cancelled'
               AND a.no_show_marked = 0"""
    params = [room_id, appointment_date]
    if exclude_appointment_id:
        query += " AND a.id != ?"
        params.append(exclude_appointment_id)
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    for row in rows:
        if check_time_overlap(start_time, end_time, row['start_time'], row['end_time']):
            return dict(row)
    return None

def lift_cooldown(anonymous_user_id, operator_id, remark=''):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM anonymous_users WHERE id = ?", (anonymous_user_id,))
    au = c.fetchone()
    if au and au['cooldown_until']:
        old_cooldown = au['cooldown_until']
        c.execute("UPDATE anonymous_users SET cooldown_until = NULL, cooldown_reason = NULL WHERE id = ?", (anonymous_user_id,))
        c.execute("""INSERT INTO intervention_records 
            (anonymous_user_id, anonymous_code, operator_id, action_type, remark, old_status, new_status)
            VALUES (?,?,?,?,?,?,?)""",
            (anonymous_user_id, au['anonymous_code'], operator_id, 'lift_cooldown',
             remark, f'cooldown until {old_cooldown}', 'normal'))
    conn.commit()
    conn.close()

def dict_row(row):
    return dict(row) if row else None

def dict_rows(rows):
    return [dict(r) for r in rows]

def has_permission(role, permission):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM role_permissions WHERE role = ? AND permission = ?", (role, permission))
    result = c.fetchone()['cnt'] > 0
    conn.close()
    return result

def get_role_permissions(role):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT permission FROM role_permissions WHERE role = ?", (role,))
    perms = [row['permission'] for row in c.fetchall()]
    conn.close()
    return perms

def calculate_risk_level(anonymous_user_id):
    from config import RISK_LEVEL_HIGH_THRESHOLD, RISK_LEVEL_MEDIUM_THRESHOLD, ABNORMAL_CANCEL_RATE_THRESHOLD
    conn = get_conn()
    c = conn.cursor()
    
    c.execute("SELECT no_show_count FROM anonymous_users WHERE id = ?", (anonymous_user_id,))
    au = c.fetchone()
    if not au:
        conn.close()
        return 'low', '数据不足'
    
    no_show_count = au['no_show_count']
    
    thirty_days_ago = (date.today() - timedelta(days=30)).isoformat()
    c.execute("""SELECT COUNT(*) as total,
                        SUM(CASE WHEN no_show_marked = 1 THEN 1 ELSE 0 END) as noshow,
                        SUM(CASE WHEN checkin_status = 'cancelled' THEN 1 ELSE 0 END) as cancelled
                 FROM appointments 
                 WHERE anonymous_user_id = ? 
                 AND appointment_date >= ?
                 AND checkin_status != 'cancelled' OR (checkin_status = 'cancelled' AND anonymous_user_id = ? AND appointment_date >= ?)""",
              (anonymous_user_id, thirty_days_ago, anonymous_user_id, thirty_days_ago))
    
    stats = c.fetchone()
    total = stats['total'] if stats else 0
    noshow_count = stats['noshow'] if stats else 0
    cancelled_count = stats['cancelled'] if stats else 0
    
    risk_level = 'low'
    reasons = []
    
    if no_show_count >= RISK_LEVEL_HIGH_THRESHOLD:
        risk_level = 'high'
        reasons.append(f'连续失约{no_show_count}次')
    elif no_show_count >= RISK_LEVEL_MEDIUM_THRESHOLD:
        risk_level = 'medium'
        reasons.append(f'连续失约{no_show_count}次')
    
    if total > 5 and noshow_count / total > 0.3:
        if risk_level != 'high':
            risk_level = 'high' if risk_level == 'medium' else 'medium'
        reasons.append(f'近30天失约率{round(noshow_count/total*100,1)}%')
    
    if total > 3 and cancelled_count / total > ABNORMAL_CANCEL_RATE_THRESHOLD:
        if risk_level == 'low':
            risk_level = 'medium'
        reasons.append(f'近30天取消率{round(cancelled_count/total*100,1)}%')
    
    conn.close()
    return risk_level, '；'.join(reasons) if reasons else '正常'

def update_risk_level(anonymous_user_id):
    risk_level, risk_reason = calculate_risk_level(anonymous_user_id)
    conn = get_conn()
    c = conn.cursor()
    c.execute("""UPDATE anonymous_users 
                 SET risk_level = ?, risk_reason = ?, risk_updated_at = ? 
                 WHERE id = ?""",
              (risk_level, risk_reason, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), anonymous_user_id))
    conn.commit()
    conn.close()
    return risk_level, risk_reason

def create_risk_warning(anonymous_user_id, anonymous_code, warning_type, risk_level, description, appointment_id=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""INSERT INTO risk_warnings 
                 (anonymous_user_id, anonymous_code, warning_type, risk_level, description, appointment_id)
                 VALUES (?, ?, ?, ?, ?, ?)""",
              (anonymous_user_id, anonymous_code, warning_type, risk_level, description, appointment_id))
    warning_id = c.lastrowid
    
    c.execute("""INSERT INTO notifications (user_id, notification_type, title, content, related_appointment_id)
                 SELECT u.id, 'risk_warning', ?, ?, ?
                 FROM users u 
                 WHERE u.role IN ('admin', 'intervention')""",
              (f'风险预警：{warning_type}', description, appointment_id))
    
    conn.commit()
    conn.close()
    return warning_id

def get_unresolved_risk_warnings(limit=50):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT rw.*, au.no_show_count, au.cooldown_until
                 FROM risk_warnings rw
                 LEFT JOIN anonymous_users au ON rw.anonymous_user_id = au.id
                 WHERE rw.is_resolved = 0
                 ORDER BY 
                    CASE rw.risk_level 
                        WHEN 'high' THEN 1 
                        WHEN 'medium' THEN 2 
                        ELSE 3 
                    END,
                    rw.created_at DESC
                 LIMIT ?""", (limit,))
    warnings = dict_rows(c.fetchall())
    conn.close()
    return warnings

def resolve_risk_warning(warning_id, operator_id, resolution_note=''):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""UPDATE risk_warnings 
                 SET is_resolved = 1, resolved_by = ?, resolved_at = ?, resolution_note = ?
                 WHERE id = ?""",
              (operator_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), resolution_note, warning_id))
    conn.commit()
    conn.close()

def check_abnormal_booking(anonymous_code, target_date):
    from config import ABNORMAL_BOOKING_DAILY_LIMIT, ABNORMAL_BOOKING_WEEKLY_LIMIT
    conn = get_conn()
    c = conn.cursor()
    
    c.execute("""SELECT COUNT(*) as cnt FROM appointments 
                 WHERE anonymous_code = ? AND appointment_date = ?
                 AND checkin_status != 'cancelled' AND no_show_marked = 0""",
              (anonymous_code, target_date))
    daily_count = c.fetchone()['cnt']
    
    target_dt = datetime.strptime(target_date, '%Y-%m-%d').date()
    week_start = (target_dt - timedelta(days=target_dt.weekday())).isoformat()
    week_end = (target_dt + timedelta(days=6 - target_dt.weekday())).isoformat()
    
    c.execute("""SELECT COUNT(*) as cnt FROM appointments 
                 WHERE anonymous_code = ? AND appointment_date BETWEEN ? AND ?
                 AND checkin_status != 'cancelled' AND no_show_marked = 0""",
              (anonymous_code, week_start, week_end))
    weekly_count = c.fetchone()['cnt']
    
    conn.close()
    
    is_abnormal = False
    reasons = []
    
    if daily_count >= ABNORMAL_BOOKING_DAILY_LIMIT:
        is_abnormal = True
        reasons.append(f'当日预约{daily_count}次，超过每日{ABNORMAL_BOOKING_DAILY_LIMIT}次限制')
    
    if weekly_count >= ABNORMAL_BOOKING_WEEKLY_LIMIT:
        is_abnormal = True
        reasons.append(f'本周预约{weekly_count}次，超过每周{ABNORMAL_BOOKING_WEEKLY_LIMIT}次限制')
    
    return is_abnormal, reasons

def create_notification(user_id, notification_type, title, content, related_appointment_id=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""INSERT INTO notifications 
                 (user_id, notification_type, title, content, related_appointment_id)
                 VALUES (?, ?, ?, ?, ?)""",
              (user_id, notification_type, title, content, related_appointment_id))
    notif_id = c.lastrowid
    conn.commit()
    conn.close()
    return notif_id

def get_user_notifications(user_id, unread_only=False, limit=20):
    conn = get_conn()
    c = conn.cursor()
    query = """SELECT n.*, a.appointment_no 
               FROM notifications n
               LEFT JOIN appointments a ON n.related_appointment_id = a.id
               WHERE n.user_id = ?"""
    params = [user_id]
    if unread_only:
        query += " AND n.is_read = 0"
    query += " ORDER BY n.created_at DESC LIMIT ?"
    params.append(limit)
    c.execute(query, params)
    notifs = dict_rows(c.fetchall())
    conn.close()
    return notifs

def mark_notification_read(notification_id, user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?", (notification_id, user_id))
    conn.commit()
    conn.close()

def get_unread_notification_count(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM notifications WHERE user_id = ? AND is_read = 0", (user_id,))
    count = c.fetchone()['cnt']
    conn.close()
    return count

def get_checkin_reminders(target_time=None):
    from config import CHECKIN_REMINDER_MINUTES_BEFORE
    if target_time is None:
        target_time = datetime.now()
    target_date = target_time.date().isoformat()
    remind_time = (target_time + timedelta(minutes=CHECKIN_REMINDER_MINUTES_BEFORE)).strftime('%H:%M')
    
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT a.*, r.room_number, cou.name as counselor_name 
                 FROM appointments a
                 JOIN rooms r ON a.room_id = r.id
                 JOIN counselors cou ON a.counselor_id = cou.id
                 WHERE a.appointment_date = ?
                 AND a.start_time <= ?
                 AND a.checkin_status = 'pending'
                 AND a.no_show_marked = 0
                 AND a.reminder_sent = 0""",
              (target_date, remind_time))
    appointments = dict_rows(c.fetchall())
    conn.close()
    return appointments

def mark_reminder_sent(appointment_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE appointments SET reminder_sent = 1 WHERE id = ?", (appointment_id,))
    conn.commit()
    conn.close()

def get_late_checkins(target_time=None):
    from config import CHECKIN_ANOMALY_LATE_MINUTES
    if target_time is None:
        target_time = datetime.now()
    target_date = target_time.date().isoformat()
    late_time = (target_time - timedelta(minutes=CHECKIN_ANOMALY_LATE_MINUTES)).strftime('%H:%M')
    
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT a.*, r.room_number, cou.name as counselor_name 
                 FROM appointments a
                 JOIN rooms r ON a.room_id = r.id
                 JOIN counselors cou ON a.counselor_id = cou.id
                 WHERE a.appointment_date = ?
                 AND a.start_time <= ?
                 AND a.checkin_status = 'pending'
                 AND a.no_show_marked = 0
                 AND a.is_abnormal = 0""",
              (target_date, late_time))
    appointments = dict_rows(c.fetchall())
    conn.close()
    return appointments

def mark_appointment_abnormal(appointment_id, reason):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE appointments SET is_abnormal = 1, abnormal_reason = ? WHERE id = ?", (reason, appointment_id))
    conn.commit()
    conn.close()

def calculate_room_utilization(room_id, start_date, end_date):
    conn = get_conn()
    c = conn.cursor()
    
    c.execute("SELECT * FROM rooms WHERE id = ?", (room_id,))
    room = dict_row(c.fetchone())
    if not room:
        conn.close()
        return None
    
    c.execute("""SELECT 
                    COUNT(*) as appointment_count,
                    SUM(CASE WHEN checkin_status = 'checked_in' THEN 1 ELSE 0 END) as checked_count,
                    SUM(CASE WHEN no_show_marked = 1 THEN 1 ELSE 0 END) as noshow_count,
                    SUM(CASE WHEN checkin_status = 'cancelled' THEN 1 ELSE 0 END) as cancelled_count
                 FROM appointments 
                 WHERE room_id = ? AND appointment_date BETWEEN ? AND ?
                 AND schedule_id IS NOT NULL""",
              (room_id, start_date, end_date))
    stats = dict_row(c.fetchone())
    
    c.execute("""SELECT COUNT(*) as total_slots,
                        SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) as active_slots
                 FROM schedules WHERE room_id = ? AND schedule_date BETWEEN ? AND ?""",
              (room_id, start_date, end_date))
    slot_stats = dict_row(c.fetchone())
    
    conn.close()
    
    from datetime import datetime, timedelta as td
    start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
    end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()
    total_days = (end_dt - start_dt).days + 1
    max_hours = total_days * ROOM_UTILIZATION_HOURS_PER_DAY
    
    appointment_count = stats['appointment_count'] if stats else 0
    utilization_rate = round(appointment_count / max(slot_stats['active_slots'] if slot_stats else 1, 1) * 100, 1)
    
    return {
        'room': room,
        'appointment_count': appointment_count,
        'checked_count': stats['checked_count'] if stats else 0,
        'noshow_count': stats['noshow_count'] if stats else 0,
        'cancelled_count': stats['cancelled_count'] if stats else 0,
        'total_slots': slot_stats['total_slots'] if slot_stats else 0,
        'active_slots': slot_stats['active_slots'] if slot_stats else 0,
        'utilization_rate': utilization_rate,
        'total_days': total_days,
    }

def get_noshow_trend(start_date, end_date):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT appointment_date,
                        COUNT(*) as total,
                        SUM(CASE WHEN no_show_marked = 1 THEN 1 ELSE 0 END) as noshow,
                        SUM(CASE WHEN checkin_status = 'checked_in' THEN 1 ELSE 0 END) as checked
                 FROM appointments
                 WHERE appointment_date BETWEEN ? AND ?
                 GROUP BY appointment_date
                 ORDER BY appointment_date""",
              (start_date, end_date))
    rows = dict_rows(c.fetchall())
    conn.close()
    
    for row in rows:
        row['noshow_rate'] = round(row['noshow'] / row['total'] * 100, 1) if row['total'] > 0 else 0
        row['attend_rate'] = round(row['checked'] / row['total'] * 100, 1) if row['total'] > 0 else 0
    
    return rows

def get_high_risk_time_slots(start_date, end_date):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT 
                    SUBSTR(start_time, 1, 2) as hour_slot,
                    COUNT(*) as total,
                    SUM(CASE WHEN no_show_marked = 1 THEN 1 ELSE 0 END) as noshow,
                    SUM(CASE WHEN checkin_status = 'checked_in' THEN 1 ELSE 0 END) as checked
                 FROM appointments
                 WHERE appointment_date BETWEEN ? AND ?
                 GROUP BY hour_slot
                 ORDER BY noshow DESC, total DESC""",
              (start_date, end_date))
    rows = dict_rows(c.fetchall())
    conn.close()
    
    for row in rows:
        row['noshow_rate'] = round(row['noshow'] / row['total'] * 100, 1) if row['total'] > 0 else 0
        row['time_label'] = f"{row['hour_slot']}:00 - {int(row['hour_slot']) + 1}:00"
    
    return rows

def get_weekly_report(week_offset=0):
    today = date.today()
    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    week_start = monday.isoformat()
    week_end = (monday + timedelta(days=6)).isoformat()
    
    conn = get_conn()
    c = conn.cursor()
    
    c.execute("""SELECT r.id, r.room_number, r.room_type,
                        COUNT(a.id) as usage_count,
                        SUM(CASE WHEN a.checkin_status = 'checked_in' THEN 1 ELSE 0 END) as checked_count,
                        SUM(CASE WHEN a.no_show_marked = 1 THEN 1 ELSE 0 END) as noshow_count
                 FROM rooms r
                 LEFT JOIN appointments a ON r.id = a.room_id 
                     AND a.appointment_date BETWEEN ? AND ?
                     AND a.checkin_status != 'cancelled'
                 GROUP BY r.id ORDER BY usage_count DESC""",
              (week_start, week_end))
    room_usage = dict_rows(c.fetchall())
    
    c.execute("""SELECT 
                    SUBSTR(start_time, 1, 2) as hour_slot,
                    COUNT(*) as total_appointments,
                    SUM(CASE WHEN no_show_marked = 1 THEN 1 ELSE 0 END) as noshow_count
                 FROM appointments
                 WHERE appointment_date BETWEEN ? AND ?
                 GROUP BY hour_slot
                 ORDER BY noshow_count DESC, total_appointments DESC""",
              (week_start, week_end))
    time_slots = dict_rows(c.fetchall())
    for ts in time_slots:
        ts['noshow_rate'] = round(ts['noshow_count'] / ts['total_appointments'] * 100, 1) if ts['total_appointments'] > 0 else 0
        ts['time_label'] = f"{ts['hour_slot']}:00 - {int(ts['hour_slot']) + 1}:00"
    
    c.execute("""SELECT appointment_date,
                        COUNT(*) as total,
                        SUM(CASE WHEN no_show_marked = 1 THEN 1 ELSE 0 END) as noshow,
                        SUM(CASE WHEN checkin_status = 'checked_in' THEN 1 ELSE 0 END) as checked,
                        SUM(CASE WHEN checkin_status = 'cancelled' THEN 1 ELSE 0 END) as cancelled
                 FROM appointments
                 WHERE appointment_date BETWEEN ? AND ?
                 GROUP BY appointment_date
                 ORDER BY appointment_date""",
              (week_start, week_end))
    daily_stats = dict_rows(c.fetchall())
    for ds in daily_stats:
        ds['noshow_rate'] = round(ds['noshow'] / ds['total'] * 100, 1) if ds['total'] > 0 else 0
        ds['attend_rate'] = round(ds['checked'] / ds['total'] * 100, 1) if ds['total'] > 0 else 0
    
    c.execute("SELECT COUNT(*) as cnt FROM risk_warnings WHERE date(created_at) BETWEEN ? AND ?",
              (week_start, week_end))
    risk_count = c.fetchone()['cnt']
    
    conn.close()
    
    total_appts = sum(d['total'] for d in daily_stats)
    total_noshow = sum(d['noshow'] for d in daily_stats)
    overall_noshow_rate = round(total_noshow / total_appts * 100, 1) if total_appts > 0 else 0
    
    high_risk_slots = [ts for ts in time_slots if ts['noshow_rate'] >= 30][:3]
    
    return {
        'week_start': week_start,
        'week_end': week_end,
        'room_usage': room_usage,
        'time_slots': time_slots,
        'high_risk_slots': high_risk_slots,
        'daily_stats': daily_stats,
        'total_appointments': total_appts,
        'total_noshow': total_noshow,
        'overall_noshow_rate': overall_noshow_rate,
        'risk_warning_count': risk_count,
    }

def get_monthly_report(month_offset=0):
    from calendar import monthrange
    today = date.today()
    target_month = today.replace(day=1)
    for _ in range(abs(month_offset)):
        if month_offset > 0:
            if target_month.month == 12:
                target_month = target_month.replace(year=target_month.year + 1, month=1)
            else:
                target_month = target_month.replace(month=target_month.month + 1)
        else:
            if target_month.month == 1:
                target_month = target_month.replace(year=target_month.year - 1, month=12)
            else:
                target_month = target_month.replace(month=target_month.month - 1)
    
    month_start = target_month.isoformat()
    last_day = monthrange(target_month.year, target_month.month)[1]
    month_end = target_month.replace(day=last_day).isoformat()
    
    conn = get_conn()
    c = conn.cursor()
    
    c.execute("""SELECT r.id, r.room_number, r.room_type,
                        COUNT(a.id) as usage_count,
                        SUM(CASE WHEN a.checkin_status = 'checked_in' THEN 1 ELSE 0 END) as checked_count,
                        SUM(CASE WHEN a.no_show_marked = 1 THEN 1 ELSE 0 END) as noshow_count,
                        SUM(CASE WHEN a.checkin_status = 'cancelled' THEN 1 ELSE 0 END) as cancelled_count
                 FROM rooms r
                 LEFT JOIN appointments a ON r.id = a.room_id 
                     AND a.appointment_date BETWEEN ? AND ?
                 GROUP BY r.id ORDER BY usage_count DESC""",
              (month_start, month_end))
    room_usage = dict_rows(c.fetchall())
    
    total_slots_per_room = {}
    c.execute("""SELECT room_id, COUNT(*) as slot_count
                 FROM schedules WHERE schedule_date BETWEEN ? AND ? AND status = 'active'
                 GROUP BY room_id""",
              (month_start, month_end))
    for row in c.fetchall():
        total_slots_per_room[row['room_id']] = row['slot_count']
    
    for ru in room_usage:
        total_slots = total_slots_per_room.get(ru['id'], 0)
        ru['total_slots'] = total_slots
        ru['utilization_rate'] = round(ru['usage_count'] / total_slots * 100, 1) if total_slots > 0 else 0
    
    c.execute("""SELECT 
                    SUBSTR(start_time, 1, 2) as hour_slot,
                    COUNT(*) as total_appointments,
                    SUM(CASE WHEN no_show_marked = 1 THEN 1 ELSE 0 END) as noshow_count
                 FROM appointments
                 WHERE appointment_date BETWEEN ? AND ?
                 GROUP BY hour_slot
                 ORDER BY noshow_count DESC, total_appointments DESC""",
              (month_start, month_end))
    time_slots = dict_rows(c.fetchall())
    for ts in time_slots:
        ts['noshow_rate'] = round(ts['noshow_count'] / ts['total_appointments'] * 100, 1) if ts['total_appointments'] > 0 else 0
        ts['time_label'] = f"{ts['hour_slot']}:00 - {int(ts['hour_slot']) + 1}:00"
    
    c.execute("""SELECT strftime('%W', appointment_date) as week_num,
                        MIN(appointment_date) as week_start,
                        COUNT(*) as total,
                        SUM(CASE WHEN no_show_marked = 1 THEN 1 ELSE 0 END) as noshow,
                        SUM(CASE WHEN checkin_status = 'checked_in' THEN 1 ELSE 0 END) as checked
                 FROM appointments
                 WHERE appointment_date BETWEEN ? AND ?
                 GROUP BY week_num
                 ORDER BY week_num""",
              (month_start, month_end))
    weekly_trend = dict_rows(c.fetchall())
    for wt in weekly_trend:
        wt['noshow_rate'] = round(wt['noshow'] / wt['total'] * 100, 1) if wt['total'] > 0 else 0
        wt['attend_rate'] = round(wt['checked'] / wt['total'] * 100, 1) if wt['total'] > 0 else 0
    
    c.execute("SELECT COUNT(*) as cnt FROM risk_warnings WHERE date(created_at) BETWEEN ? AND ?",
              (month_start, month_end))
    risk_count = c.fetchone()['cnt']
    
    c.execute("SELECT COUNT(*) as cnt FROM anonymous_users WHERE risk_level = 'high'")
    high_risk_users = c.fetchone()['cnt']
    
    conn.close()
    
    total_appts = sum(wt['total'] for wt in weekly_trend)
    total_noshow = sum(wt['noshow'] for wt in weekly_trend)
    overall_noshow_rate = round(total_noshow / total_appts * 100, 1) if total_appts > 0 else 0
    
    high_risk_slots = [ts for ts in time_slots if ts['noshow_rate'] >= 30][:5]
    
    return {
        'month_start': month_start,
        'month_end': month_end,
        'month_label': target_month.strftime('%Y年%m月'),
        'room_usage': room_usage,
        'time_slots': time_slots,
        'high_risk_slots': high_risk_slots,
        'weekly_trend': weekly_trend,
        'total_appointments': total_appts,
        'total_noshow': total_noshow,
        'overall_noshow_rate': overall_noshow_rate,
        'risk_warning_count': risk_count,
        'high_risk_users': high_risk_users,
    }
