import sqlite3
import os
import hashlib
from datetime import datetime, timedelta
from config import DB_PATH, NO_SHOW_THRESHOLD, COOLDOWN_DAYS

def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

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

    c.execute('''CREATE INDEX IF NOT EXISTS idx_appt_date ON appointments(appointment_date)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_appt_code ON appointments(anonymous_code)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_appt_status ON appointments(checkin_status)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_sched_date ON schedules(schedule_date)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_anony_code ON anonymous_users(anonymous_code)''')

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
