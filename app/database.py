import sqlite3
import os
import hashlib
from datetime import datetime, timedelta, date
from config import DB_PATH, NO_SHOW_THRESHOLD, COOLDOWN_DAYS, ROOM_UTILIZATION_HOURS_PER_DAY

def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
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

    c.execute('''CREATE TABLE IF NOT EXISTS followup_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_text TEXT NOT NULL,
        question_type TEXT NOT NULL DEFAULT 'text',
        options TEXT,
        sort_order INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS followup_surveys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        appointment_id INTEGER NOT NULL,
        anonymous_code TEXT NOT NULL,
        anonymous_user_id INTEGER,
        counselor_id INTEGER,
        satisfaction_score INTEGER,
        rebook_willingness TEXT DEFAULT 'undecided',
        responses TEXT,
        comment TEXT,
        is_abnormal INTEGER DEFAULT 0,
        abnormal_reason TEXT,
        is_high_risk INTEGER DEFAULT 0,
        high_risk_reason TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE CASCADE,
        FOREIGN KEY (anonymous_user_id) REFERENCES anonymous_users(id),
        FOREIGN KEY (counselor_id) REFERENCES counselors(id)
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

    c.execute('''CREATE TABLE IF NOT EXISTS supervision_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_no TEXT UNIQUE NOT NULL,
        task_type TEXT NOT NULL,
        priority TEXT NOT NULL DEFAULT 'normal',
        title TEXT NOT NULL,
        description TEXT,
        anonymous_user_id INTEGER,
        anonymous_code TEXT,
        appointment_id INTEGER,
        followup_survey_id INTEGER,
        risk_warning_id INTEGER,
        assigned_to INTEGER,
        assigned_by INTEGER,
        status TEXT NOT NULL DEFAULT 'pending',
        deadline TIMESTAMP,
        completed_at TIMESTAMP,
        completion_note TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (anonymous_user_id) REFERENCES anonymous_users(id),
        FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE SET NULL,
        FOREIGN KEY (followup_survey_id) REFERENCES followup_surveys(id) ON DELETE SET NULL,
        FOREIGN KEY (risk_warning_id) REFERENCES risk_warnings(id) ON DELETE SET NULL,
        FOREIGN KEY (assigned_to) REFERENCES users(id) ON DELETE SET NULL,
        FOREIGN KEY (assigned_by) REFERENCES users(id) ON DELETE SET NULL
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS supervision_task_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER NOT NULL,
        operator_id INTEGER,
        action_type TEXT NOT NULL,
        remark TEXT,
        old_status TEXT,
        new_status TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (task_id) REFERENCES supervision_tasks(id) ON DELETE CASCADE,
        FOREIGN KEY (operator_id) REFERENCES users(id) ON DELETE SET NULL
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS intervention_archives (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        archive_no TEXT UNIQUE NOT NULL,
        anonymous_user_id INTEGER,
        anonymous_code TEXT,
        appointment_id INTEGER,
        risk_warning_id INTEGER,
        supervision_task_id INTEGER,
        counselor_id INTEGER,
        intervention_type TEXT NOT NULL,
        intervention_level TEXT,
        intervention_methods TEXT,
        intervention_content TEXT,
        intervention_effect TEXT,
        follow_up_plan TEXT,
        is_closed INTEGER DEFAULT 0,
        closed_by INTEGER,
        closed_at TIMESTAMP,
        closing_remark TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (anonymous_user_id) REFERENCES anonymous_users(id),
        FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE SET NULL,
        FOREIGN KEY (risk_warning_id) REFERENCES risk_warnings(id) ON DELETE SET NULL,
        FOREIGN KEY (supervision_task_id) REFERENCES supervision_tasks(id) ON DELETE SET NULL,
        FOREIGN KEY (counselor_id) REFERENCES counselors(id) ON DELETE SET NULL,
        FOREIGN KEY (closed_by) REFERENCES users(id) ON DELETE SET NULL
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS high_risk_tracking (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tracking_no TEXT UNIQUE NOT NULL,
        anonymous_user_id INTEGER NOT NULL,
        anonymous_code TEXT NOT NULL,
        risk_level TEXT NOT NULL DEFAULT 'high',
        initial_risk_reason TEXT,
        current_status TEXT NOT NULL DEFAULT 'monitoring',
        assigned_counselor_id INTEGER,
        assigned_supervisor_id INTEGER,
        next_followup_date DATE,
        last_followup_date DATE,
        followup_count INTEGER DEFAULT 0,
        is_closed INTEGER DEFAULT 0,
        closed_by INTEGER,
        closed_at TIMESTAMP,
        closing_reason TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (anonymous_user_id) REFERENCES anonymous_users(id) ON DELETE CASCADE,
        FOREIGN KEY (assigned_counselor_id) REFERENCES counselors(id) ON DELETE SET NULL,
        FOREIGN KEY (assigned_supervisor_id) REFERENCES users(id) ON DELETE SET NULL,
        FOREIGN KEY (closed_by) REFERENCES users(id) ON DELETE SET NULL
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS high_risk_tracking_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tracking_id INTEGER NOT NULL,
        operator_id INTEGER,
        log_type TEXT NOT NULL,
        content TEXT,
        mood_score INTEGER,
        risk_assessment TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tracking_id) REFERENCES high_risk_tracking(id) ON DELETE CASCADE,
        FOREIGN KEY (operator_id) REFERENCES users(id) ON DELETE SET NULL
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS rebook_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        anonymous_user_id INTEGER NOT NULL,
        anonymous_code TEXT NOT NULL,
        first_appointment_id INTEGER,
        first_counselor_id INTEGER,
        rebook_appointment_id INTEGER,
        rebook_counselor_id INTEGER,
        days_between INTEGER,
        rebook_reason TEXT,
        is_same_counselor INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (anonymous_user_id) REFERENCES anonymous_users(id) ON DELETE CASCADE,
        FOREIGN KEY (first_appointment_id) REFERENCES appointments(id) ON DELETE SET NULL,
        FOREIGN KEY (rebook_appointment_id) REFERENCES appointments(id) ON DELETE SET NULL
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

    _add_column_if_not_exists('followup_surveys', 'abnormal_grade TEXT DEFAULT \'normal\'')
    _add_column_if_not_exists('followup_surveys', 'abnormal_grade_reason TEXT')
    _add_column_if_not_exists('followup_surveys', 'priority_level TEXT DEFAULT \'normal\'')

    _add_column_if_not_exists('supervision_tasks', 'last_reminder_sent TIMESTAMP')

    _add_column_if_not_exists('notifications', 'related_supervision_task_id INTEGER')

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
    c.execute('''CREATE INDEX IF NOT EXISTS idx_followup_appt ON followup_surveys(appointment_id)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_followup_code ON followup_surveys(anonymous_code)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_followup_counselor ON followup_surveys(counselor_id)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_followup_abnormal ON followup_surveys(is_abnormal)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_followup_highrisk ON followup_surveys(is_high_risk)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_followup_score ON followup_surveys(satisfaction_score)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_followup_created ON followup_surveys(created_at)''')

    c.execute('''CREATE INDEX IF NOT EXISTS idx_supervision_status ON supervision_tasks(status)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_supervision_priority ON supervision_tasks(priority)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_supervision_assigned ON supervision_tasks(assigned_to, status)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_supervision_deadline ON supervision_tasks(deadline)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_supervision_anonymous ON supervision_tasks(anonymous_user_id)''')

    c.execute('''CREATE INDEX IF NOT EXISTS idx_archive_closed ON intervention_archives(is_closed)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_archive_anonymous ON intervention_archives(anonymous_user_id)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_archive_created ON intervention_archives(created_at)''')

    c.execute('''CREATE INDEX IF NOT EXISTS idx_hirt_status ON high_risk_tracking(current_status)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_hirt_anonymous ON high_risk_tracking(anonymous_user_id)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_hirt_closed ON high_risk_tracking(is_closed)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_hirt_followup ON high_risk_tracking(next_followup_date)''')

    c.execute('''CREATE INDEX IF NOT EXISTS idx_rebook_anonymous ON rebook_records(anonymous_user_id)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_rebook_counselor ON rebook_records(first_counselor_id)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_rebook_created ON rebook_records(created_at)''')

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
            'view_followup', 'manage_followup', 'view_followup_analytics',
            'view_supervision', 'manage_supervision', 'assign_supervision',
            'view_intervention_archives', 'manage_intervention_archives',
            'view_high_risk_tracking', 'manage_high_risk_tracking',
            'view_quality_comparison', 'view_rebook_analysis',
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
            'view_followup', 'view_followup_analytics',
            'view_supervision',
            'view_quality_comparison', 'view_rebook_analysis',
        ],
        'intervention': [
            'view_dashboard',
            'view_appointments',
            'view_interventions', 'manage_interventions', 'lift_cooldown',
            'view_analytics',
            'view_risk_warnings', 'manage_risk_warnings',
            'view_notifications',
            'view_followup', 'manage_followup', 'view_followup_analytics',
            'view_supervision', 'manage_supervision',
            'view_intervention_archives', 'manage_intervention_archives',
            'view_high_risk_tracking', 'manage_high_risk_tracking',
            'view_quality_comparison', 'view_rebook_analysis',
        ],
        'counselor': [
            'view_dashboard',
            'view_schedules',
            'view_appointments',
            'view_notifications',
            'view_followup', 'view_followup_analytics',
            'view_quality_comparison',
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

    c.execute("SELECT COUNT(*) FROM followup_questions")
    if c.fetchone()[0] == 0:
        questions_data = [
            ('咨询后您的情绪状态如何？', 'choice', '["明显好转","有所改善","没有变化","感到更差"]', 1),
            ('您对咨询师的专业能力评价如何？', 'rating', None, 2),
            ('您对咨询环境（私密性、舒适度）的评价？', 'rating', None, 3),
            ('您是否感到被充分倾听和理解？', 'choice', '["完全如此","基本如此","部分如此","不太如此"]', 4),
            ('您对本次咨询还有其他建议或反馈吗？', 'text', None, 5),
        ]
        c.executemany("INSERT INTO followup_questions (question_text, question_type, options, sort_order) VALUES (?,?,?,?)", questions_data)

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
    c.execute("""SELECT 
                    SUM(CASE WHEN checkin_status != 'cancelled' THEN 1 ELSE 0 END) as total_valid,
                    SUM(CASE WHEN no_show_marked = 1 AND checkin_status != 'cancelled' THEN 1 ELSE 0 END) as noshow,
                    SUM(CASE WHEN checkin_status = 'cancelled' THEN 1 ELSE 0 END) as cancelled
                 FROM appointments 
                 WHERE anonymous_user_id = ? 
                 AND appointment_date >= ?""",
              (anonymous_user_id, thirty_days_ago))
    
    stats = c.fetchone()
    total_valid = (stats['total_valid'] or 0) if stats else 0
    noshow_count = (stats['noshow'] or 0) if stats else 0
    cancelled_count = (stats['cancelled'] or 0) if stats else 0
    total_with_cancelled = total_valid + cancelled_count
    
    risk_level = 'low'
    reasons = []
    
    if no_show_count >= RISK_LEVEL_HIGH_THRESHOLD:
        risk_level = 'high'
        reasons.append(f'连续失约{no_show_count}次')
    elif no_show_count >= RISK_LEVEL_MEDIUM_THRESHOLD:
        risk_level = 'medium'
        reasons.append(f'连续失约{no_show_count}次')
    
    if total_valid > 5 and noshow_count / total_valid > 0.3:
        if risk_level != 'high':
            risk_level = 'high' if risk_level == 'medium' else 'medium'
        reasons.append(f'近30天失约率{round(noshow_count/total_valid*100,1)}%')
    
    if total_with_cancelled > 3 and cancelled_count / total_with_cancelled > ABNORMAL_CANCEL_RATE_THRESHOLD:
        if risk_level == 'low':
            risk_level = 'medium'
        reasons.append(f'近30天取消率{round(cancelled_count/total_with_cancelled*100,1)}%')
    
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
                   AND checkin_status != 'cancelled'
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
        valid_total = ds['total'] - ds['cancelled']
        ds['noshow_rate'] = round(ds['noshow'] / valid_total * 100, 1) if valid_total > 0 else 0
        ds['attend_rate'] = round(ds['checked'] / valid_total * 100, 1) if valid_total > 0 else 0
    
    c.execute("SELECT COUNT(*) as cnt FROM risk_warnings WHERE date(created_at) BETWEEN ? AND ?",
              (week_start, week_end))
    risk_count = c.fetchone()['cnt']
    
    conn.close()
    
    total_appts = sum(d['total'] - d['cancelled'] for d in daily_stats)
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
                        COUNT(CASE WHEN a.checkin_status != 'cancelled' THEN a.id ELSE NULL END) as usage_count,
                        SUM(CASE WHEN a.checkin_status = 'checked_in' THEN 1 ELSE 0 END) as checked_count,
                        SUM(CASE WHEN a.no_show_marked = 1 AND a.checkin_status != 'cancelled' THEN 1 ELSE 0 END) as noshow_count,
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
                   AND checkin_status != 'cancelled'
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
                        SUM(CASE WHEN checkin_status = 'checked_in' THEN 1 ELSE 0 END) as checked,
                        SUM(CASE WHEN checkin_status = 'cancelled' THEN 1 ELSE 0 END) as cancelled
                 FROM appointments
                 WHERE appointment_date BETWEEN ? AND ?
                 GROUP BY week_num
                 ORDER BY week_num""",
              (month_start, month_end))
    weekly_trend = dict_rows(c.fetchall())
    for wt in weekly_trend:
        valid_total = wt['total'] - wt['cancelled']
        wt['noshow_rate'] = round(wt['noshow'] / valid_total * 100, 1) if valid_total > 0 else 0
        wt['attend_rate'] = round(wt['checked'] / valid_total * 100, 1) if valid_total > 0 else 0
    
    c.execute("SELECT COUNT(*) as cnt FROM risk_warnings WHERE date(created_at) BETWEEN ? AND ?",
              (month_start, month_end))
    risk_count = c.fetchone()['cnt']
    
    c.execute("SELECT COUNT(*) as cnt FROM anonymous_users WHERE risk_level = 'high'")
    high_risk_users = c.fetchone()['cnt']
    
    conn.close()
    
    total_appts = sum(wt['total'] - wt['cancelled'] for wt in weekly_trend)
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

def get_active_followup_questions():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM followup_questions WHERE is_active = 1 ORDER BY sort_order, id")
    rows = dict_rows(c.fetchall())
    conn.close()
    return rows

def get_all_followup_questions():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM followup_questions ORDER BY sort_order, id")
    rows = dict_rows(c.fetchall())
    conn.close()
    return rows

def add_followup_question(question_text, question_type, options=None, sort_order=0):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO followup_questions (question_text, question_type, options, sort_order) VALUES (?,?,?,?)",
              (question_text, question_type, options, sort_order))
    conn.commit()
    qid = c.lastrowid
    conn.close()
    return qid

def update_followup_question(question_id, question_text=None, question_type=None, options=None, sort_order=None, is_active=None):
    conn = get_conn()
    c = conn.cursor()
    updates = []
    params = []
    if question_text is not None:
        updates.append("question_text = ?")
        params.append(question_text)
    if question_type is not None:
        updates.append("question_type = ?")
        params.append(question_type)
    if options is not None:
        updates.append("options = ?")
        params.append(options)
    if sort_order is not None:
        updates.append("sort_order = ?")
        params.append(sort_order)
    if is_active is not None:
        updates.append("is_active = ?")
        params.append(is_active)
    if not updates:
        conn.close()
        return
    params.append(question_id)
    c.execute(f"UPDATE followup_questions SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()

def get_eligible_appointments_for_followup(anonymous_code):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    c.execute("""SELECT a.*, cou.name as counselor_name, r.room_number
                 FROM appointments a
                 JOIN counselors cou ON a.counselor_id = cou.id
                 JOIN rooms r ON a.room_id = r.id
                 WHERE a.anonymous_code = ?
                 AND a.checkin_status = 'checked_in'
                 AND a.id NOT IN (SELECT appointment_id FROM followup_surveys)
                 AND DATETIME(a.appointment_date || ' ' || a.end_time) <= ?
                 ORDER BY a.appointment_date DESC, a.start_time DESC""",
              (anonymous_code, now))
    rows = dict_rows(c.fetchall())
    conn.close()
    return rows

def submit_followup_survey(appointment_id, anonymous_code, anonymous_user_id, counselor_id,
                           satisfaction_score, rebook_willingness, responses, comment=''):
    import json
    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT id FROM followup_surveys WHERE appointment_id = ?", (appointment_id,))
    if c.fetchone():
        conn.close()
        return None

    is_abnormal = 0
    abnormal_reason = None
    is_high_risk = 0
    high_risk_reason = None

    if satisfaction_score is not None and satisfaction_score <= 2:
        is_abnormal = 1
        abnormal_reason = f'满意度评分偏低({satisfaction_score}分)'
        is_high_risk = 1
        high_risk_reason = f'低满意度({satisfaction_score}分)'

    responses_json = json.dumps(responses, ensure_ascii=False) if isinstance(responses, (dict, list)) else responses

    if isinstance(responses, dict):
        for key, val in responses.items():
            val_str = str(val)
            if '感到更差' in val_str or '不太如此' in val_str:
                is_abnormal = 1
                if not abnormal_reason:
                    abnormal_reason = f'回访异常反馈：{val_str}'
                if not is_high_risk:
                    is_high_risk = 1
                    high_risk_reason = f'异常反馈：{val_str}'

    if comment and len(comment) > 0:
        risk_keywords = ['自杀', '自残', '伤害', '不想活', '绝望', '崩溃', '无望']
        for kw in risk_keywords:
            if kw in comment:
                is_abnormal = 1
                is_high_risk = 1
                abnormal_reason = (abnormal_reason + '；' if abnormal_reason else '') + f'留言含高风险关键词'
                high_risk_reason = (high_risk_reason + '；' if high_risk_reason else '') + f'留言含高风险关键词：{kw}'
                break

    c.execute("""INSERT INTO followup_surveys
                 (appointment_id, anonymous_code, anonymous_user_id, counselor_id,
                  satisfaction_score, rebook_willingness, responses, comment,
                  is_abnormal, abnormal_reason, is_high_risk, high_risk_reason)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
              (appointment_id, anonymous_code, anonymous_user_id, counselor_id,
               satisfaction_score, rebook_willingness, responses_json, comment,
               is_abnormal, abnormal_reason, is_high_risk, high_risk_reason))
    survey_id = c.lastrowid

    if is_high_risk:
        c.execute("""INSERT INTO risk_warnings
                     (anonymous_user_id, anonymous_code, warning_type, risk_level, description, appointment_id)
                     VALUES (?, ?, ?, ?, ?, ?)""",
                  (anonymous_user_id, anonymous_code, 'followup_high_risk', 'high',
                   f'回访高风险预警：{high_risk_reason}', appointment_id))
        c.execute("""INSERT INTO notifications (user_id, notification_type, title, content, related_appointment_id)
                     SELECT u.id, 'followup_alert', ?, ?, ?
                     FROM users u WHERE u.role IN ('admin', 'intervention')""",
                  (f'回访高风险预警：匿名用户{anonymous_code[:4]}***',
                   f'回访发现异常反馈，需关注。原因：{high_risk_reason}', appointment_id))

    if is_abnormal and not is_high_risk:
        c.execute("""INSERT INTO notifications (user_id, notification_type, title, content, related_appointment_id)
                     SELECT u.id, 'followup_alert', ?, ?, ?
                     FROM users u WHERE u.role IN ('admin', 'intervention')""",
                  (f'回访异常反馈：匿名用户{anonymous_code[:4]}***',
                   f'回访发现异常反馈。原因：{abnormal_reason}', appointment_id))

    conn.commit()
    conn.close()
    return survey_id

def get_followup_surveys(filters=None, limit=100):
    conn = get_conn()
    c = conn.cursor()
    query = """SELECT fs.*, cou.name as counselor_name,
                      a.appointment_no, a.appointment_date, a.start_time, a.end_time
               FROM followup_surveys fs
               LEFT JOIN counselors cou ON fs.counselor_id = cou.id
               LEFT JOIN appointments a ON fs.appointment_id = a.id
               WHERE 1=1"""
    params = []
    if filters:
        if filters.get('anonymous_code'):
            query += " AND fs.anonymous_code LIKE ?"
            params.append(f"%{filters['anonymous_code']}%")
        if filters.get('counselor_id'):
            query += " AND fs.counselor_id = ?"
            params.append(filters['counselor_id'])
        if filters.get('satisfaction_min'):
            query += " AND fs.satisfaction_score >= ?"
            params.append(filters['satisfaction_min'])
        if filters.get('satisfaction_max'):
            query += " AND fs.satisfaction_score <= ?"
            params.append(filters['satisfaction_max'])
        if filters.get('rebook_willingness'):
            query += " AND fs.rebook_willingness = ?"
            params.append(filters['rebook_willingness'])
        if filters.get('is_abnormal') is not None:
            query += " AND fs.is_abnormal = ?"
            params.append(filters['is_abnormal'])
        if filters.get('is_high_risk') is not None:
            query += " AND fs.is_high_risk = ?"
            params.append(filters['is_high_risk'])
        if filters.get('date_from'):
            query += " AND fs.created_at >= ?"
            params.append(filters['date_from'])
        if filters.get('date_to'):
            query += " AND fs.created_at <= ?"
            params.append(filters['date_to'] + ' 23:59:59')
    query += " ORDER BY fs.created_at DESC LIMIT ?"
    params.append(limit)
    c.execute(query, params)
    rows = dict_rows(c.fetchall())
    conn.close()
    return rows

def get_followup_survey_by_appointment(appointment_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM followup_surveys WHERE appointment_id = ?", (appointment_id,))
    row = dict_row(c.fetchone())
    conn.close()
    return row

def mark_followup_abnormal(survey_id, is_abnormal, abnormal_reason='', is_high_risk=None, high_risk_reason=None):
    conn = get_conn()
    c = conn.cursor()
    updates = []
    params = []
    if is_abnormal is not None:
        updates.append("is_abnormal = ?")
        params.append(is_abnormal)
        updates.append("abnormal_reason = ?")
        params.append(abnormal_reason if abnormal_reason else None)
    if is_high_risk is not None:
        updates.append("is_high_risk = ?")
        params.append(is_high_risk)
        updates.append("high_risk_reason = ?")
        params.append(high_risk_reason if high_risk_reason else None)
    if updates:
        params.append(survey_id)
        c.execute(f"UPDATE followup_surveys SET {', '.join(updates)} WHERE id = ?", params)
        if is_high_risk == 1:
            c.execute("""SELECT fs.*, a.appointment_no, a.appointment_date, a.start_time
                         FROM followup_surveys fs
                         LEFT JOIN appointments a ON fs.appointment_id = a.id
                         WHERE fs.id = ?""", (survey_id,))
            row = dict_row(c.fetchone())
            if row:
                c.execute("""SELECT id FROM risk_warnings 
                             WHERE appointment_id = ? AND warning_type = 'followup_manual_high_risk' AND is_resolved = 0""",
                          (row.get('appointment_id'),))
                if not c.fetchone():
                    c.execute("""INSERT INTO risk_warnings
                                 (anonymous_user_id, anonymous_code, warning_type, risk_level, description, appointment_id)
                                 VALUES (?, ?, 'followup_manual_high_risk', 'high', ?, ?)""",
                              (row.get('anonymous_user_id'), row.get('anonymous_code'),
                               f'人工标记高风险：{high_risk_reason or abnormal_reason or "人工标记"}',
                               row.get('appointment_id')))
                    c.execute("""INSERT INTO notifications (user_id, notification_type, title, content, related_appointment_id)
                                 SELECT u.id, 'followup_alert', ?, ?, ?
                                 FROM users u WHERE u.role IN ('admin', 'intervention')""",
                              (f'回访高风险预警：人工标记',
                               f'工作人员手动标记回访为高风险。原因：{high_risk_reason or abnormal_reason or "人工标记"}',
                               row.get('appointment_id')))
    conn.commit()
    conn.close()

def get_satisfaction_trend(start_date, end_date, period='week'):
    conn = get_conn()
    c = conn.cursor()
    if period == 'week':
        group_expr = "strftime('%Y-W%W', fs.created_at)"
    elif period == 'month':
        group_expr = "strftime('%Y-%m', fs.created_at)"
    else:
        group_expr = "date(fs.created_at)"

    c.execute(f"""SELECT {group_expr} as period_label,
                         COUNT(*) as total,
                         AVG(fs.satisfaction_score) as avg_score,
                         SUM(CASE WHEN fs.satisfaction_score >= 4 THEN 1 ELSE 0 END) as high_count,
                         SUM(CASE WHEN fs.satisfaction_score <= 2 THEN 1 ELSE 0 END) as low_count
                  FROM followup_surveys fs
                  WHERE fs.satisfaction_score IS NOT NULL
                  AND date(fs.created_at) BETWEEN ? AND ?
                  GROUP BY period_label
                  ORDER BY period_label""",
              (start_date, end_date))
    rows = dict_rows(c.fetchall())
    for r in rows:
        r['avg_score'] = round(r['avg_score'], 2) if r['avg_score'] else 0
        r['high_ratio'] = round(r['high_count'] / r['total'] * 100, 1) if r['total'] > 0 else 0
        r['low_ratio'] = round(r['low_count'] / r['total'] * 100, 1) if r['total'] > 0 else 0
    conn.close()
    return rows

def get_counselor_satisfaction_distribution(start_date, end_date):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT cou.id, cou.name, cou.title,
                        COUNT(fs.id) as total_surveys,
                        AVG(fs.satisfaction_score) as avg_score,
                        SUM(CASE WHEN fs.satisfaction_score = 5 THEN 1 ELSE 0 END) as score_5,
                        SUM(CASE WHEN fs.satisfaction_score = 4 THEN 1 ELSE 0 END) as score_4,
                        SUM(CASE WHEN fs.satisfaction_score = 3 THEN 1 ELSE 0 END) as score_3,
                        SUM(CASE WHEN fs.satisfaction_score = 2 THEN 1 ELSE 0 END) as score_2,
                        SUM(CASE WHEN fs.satisfaction_score = 1 THEN 1 ELSE 0 END) as score_1,
                        SUM(CASE WHEN fs.rebook_willingness = 'yes' THEN 1 ELSE 0 END) as rebook_yes,
                        SUM(CASE WHEN fs.rebook_willingness = 'no' THEN 1 ELSE 0 END) as rebook_no,
                        SUM(CASE WHEN fs.rebook_willingness = 'undecided' THEN 1 ELSE 0 END) as rebook_undecided
                 FROM counselors cou
                 LEFT JOIN followup_surveys fs ON cou.id = fs.counselor_id
                    AND date(fs.created_at) BETWEEN ? AND ?
                 WHERE cou.is_active = 1
                 GROUP BY cou.id
                 ORDER BY avg_score DESC NULLS LAST""",
              (start_date, end_date))
    rows = dict_rows(c.fetchall())
    for r in rows:
        r['avg_score'] = round(r['avg_score'], 2) if r['avg_score'] else 0
        r['rebook_rate'] = round(r['rebook_yes'] / r['total_surveys'] * 100, 1) if r['total_surveys'] > 0 else 0
    conn.close()
    return rows

def get_abnormal_feedback_stats(start_date, end_date, period='week'):
    conn = get_conn()
    c = conn.cursor()
    if period == 'week':
        group_expr = "strftime('%Y-W%W', fs.created_at)"
    elif period == 'month':
        group_expr = "strftime('%Y-%m', fs.created_at)"
    else:
        group_expr = "date(fs.created_at)"

    c.execute(f"""SELECT {group_expr} as period_label,
                         COUNT(*) as total,
                         SUM(CASE WHEN fs.is_abnormal = 1 THEN 1 ELSE 0 END) as abnormal_count,
                         SUM(CASE WHEN fs.is_high_risk = 1 THEN 1 ELSE 0 END) as high_risk_count,
                         SUM(CASE WHEN fs.rebook_willingness = 'no' THEN 1 ELSE 0 END) as no_rebook_count
                  FROM followup_surveys fs
                  WHERE date(fs.created_at) BETWEEN ? AND ?
                  GROUP BY period_label
                  ORDER BY period_label""",
              (start_date, end_date))
    rows = dict_rows(c.fetchall())
    for r in rows:
        r['abnormal_ratio'] = round(r['abnormal_count'] / r['total'] * 100, 1) if r['total'] > 0 else 0
        r['high_risk_ratio'] = round(r['high_risk_count'] / r['total'] * 100, 1) if r['total'] > 0 else 0
        r['no_rebook_ratio'] = round(r['no_rebook_count'] / r['total'] * 100, 1) if r['total'] > 0 else 0
    conn.close()
    return rows

def get_high_risk_followup_warnings(limit=50):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT fs.*, cou.name as counselor_name,
                        a.appointment_no, a.appointment_date
                 FROM followup_surveys fs
                 LEFT JOIN counselors cou ON fs.counselor_id = cou.id
                 LEFT JOIN appointments a ON fs.appointment_id = a.id
                 WHERE fs.is_high_risk = 1
                 ORDER BY fs.created_at DESC
                 LIMIT ?""", (limit,))
    rows = dict_rows(c.fetchall())
    conn.close()
    return rows

def get_followup_summary_stats(start_date=None, end_date=None):
    conn = get_conn()
    c = conn.cursor()
    where = ""
    params = []
    if start_date and end_date:
        where = "WHERE date(created_at) BETWEEN ? AND ?"
        params = [start_date, end_date]

    c.execute(f"SELECT COUNT(*) as cnt FROM followup_surveys {where}", params)
    total = c.fetchone()['cnt']

    c.execute(f"""SELECT AVG(satisfaction_score) as avg_score,
                         SUM(CASE WHEN satisfaction_score >= 4 THEN 1 ELSE 0 END) as satisfied,
                         SUM(CASE WHEN satisfaction_score <= 2 THEN 1 ELSE 0 END) as unsatisfied,
                         SUM(CASE WHEN is_abnormal = 1 THEN 1 ELSE 0 END) as abnormal,
                         SUM(CASE WHEN is_high_risk = 1 THEN 1 ELSE 0 END) as high_risk,
                         SUM(CASE WHEN rebook_willingness = 'yes' THEN 1 ELSE 0 END) as rebook_yes,
                         SUM(CASE WHEN rebook_willingness = 'no' THEN 1 ELSE 0 END) as rebook_no,
                         SUM(CASE WHEN rebook_willingness = 'undecided' THEN 1 ELSE 0 END) as rebook_undecided
                  FROM followup_surveys {where}""", params)
    stats = dict_row(c.fetchone())

    c.execute(f"""SELECT satisfaction_score, COUNT(*) as cnt
                  FROM followup_surveys
                  WHERE satisfaction_score IS NOT NULL
                  {"AND date(created_at) BETWEEN ? AND ?" if start_date and end_date else ""}
                  GROUP BY satisfaction_score
                  ORDER BY satisfaction_score""",
              params if start_date and end_date else [])
    score_dist = dict_rows(c.fetchall())

    conn.close()

    if stats:
        stats['total'] = total
        stats['avg_score'] = round(stats['avg_score'], 2) if stats.get('avg_score') else 0
        stats['satisfied'] = stats.get('satisfied') or 0
        stats['unsatisfied'] = stats.get('unsatisfied') or 0
        stats['abnormal'] = stats.get('abnormal') or 0
        stats['high_risk'] = stats.get('high_risk') or 0
        stats['rebook_yes'] = stats.get('rebook_yes') or 0
        stats['rebook_no'] = stats.get('rebook_no') or 0
        stats['rebook_undecided'] = stats.get('rebook_undecided') or 0
        stats['satisfaction_rate'] = round(stats['satisfied'] / total * 100, 1) if total > 0 else 0
        stats['abnormal_rate'] = round(stats['abnormal'] / total * 100, 1) if total > 0 else 0
        stats['high_risk_rate'] = round(stats['high_risk'] / total * 100, 1) if total > 0 else 0
        stats['rebook_rate'] = round(stats['rebook_yes'] / total * 100, 1) if total > 0 else 0
    else:
        stats = {'total': 0, 'avg_score': 0, 'satisfied': 0, 'unsatisfied': 0,
                 'abnormal': 0, 'high_risk': 0, 'rebook_yes': 0, 'rebook_no': 0,
                 'rebook_undecided': 0, 'satisfaction_rate': 0, 'abnormal_rate': 0,
                 'high_risk_rate': 0, 'rebook_rate': 0}

    return stats, score_dist

def generate_task_no():
    now = datetime.now()
    return 'TSK' + now.strftime('%Y%m%d%H%M%S') + str(now.microsecond // 1000).zfill(3)

def generate_archive_no():
    now = datetime.now()
    return 'ARC' + now.strftime('%Y%m%d%H%M%S') + str(now.microsecond // 1000).zfill(3)

def generate_tracking_no():
    now = datetime.now()
    return 'TRK' + now.strftime('%Y%m%d%H%M%S') + str(now.microsecond // 1000).zfill(3)

def grade_followup_abnormal(survey_id):
    from config import (FOLLOWUP_GRADE_HIGH_SCORE, FOLLOWUP_GRADE_MEDIUM_SCORE,
                        FOLLOWUP_GRADE_KEYWORDS_MEDIUM, FOLLOWUP_GRADE_KEYWORDS_HIGH)
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM followup_surveys WHERE id = ?", (survey_id,))
    survey = dict_row(c.fetchone())
    if not survey:
        conn.close()
        return None

    grade = 'normal'
    reasons = []
    priority = 'normal'

    score = survey.get('satisfaction_score')
    if score is not None:
        if score <= FOLLOWUP_GRADE_HIGH_SCORE:
            grade = 'critical'
            reasons.append(f'满意度极低({score}分)')
            priority = 'urgent'
        elif score <= FOLLOWUP_GRADE_MEDIUM_SCORE:
            grade = 'important'
            reasons.append(f'满意度偏低({score}分)')
            priority = 'high'

    comment = survey.get('comment') or ''
    responses = survey.get('responses') or ''

    if isinstance(responses, str):
        try:
            responses = json.loads(responses)
        except (json.JSONDecodeError, TypeError):
            responses = {}

    all_text = comment
    if isinstance(responses, dict):
        for v in responses.values():
            all_text += ' ' + str(v)

    for kw in FOLLOWUP_GRADE_KEYWORDS_HIGH:
        if kw in all_text:
            if grade != 'critical':
                grade = 'critical'
                priority = 'urgent'
            reasons.append(f'含高风险关键词：{kw}')
            break

    if grade != 'critical':
        for kw in FOLLOWUP_GRADE_KEYWORDS_MEDIUM:
            if kw in all_text:
                if grade == 'normal':
                    grade = 'important'
                    priority = 'high'
                reasons.append(f'含关注关键词：{kw}')

    if survey.get('is_high_risk'):
        grade = 'critical'
        priority = 'urgent'
        if not reasons:
            reasons.append('系统标记为高风险')

    if survey.get('is_abnormal') and grade == 'normal':
        grade = 'general'
        priority = 'normal'
        reasons.append('回访异常反馈')

    if survey.get('rebook_willingness') == 'no' and grade == 'normal':
        grade = 'general'
        reasons.append('明确表示不复约')

    c.execute("""UPDATE followup_surveys 
                 SET abnormal_grade = ?, abnormal_grade_reason = ?, priority_level = ?
                 WHERE id = ?""",
              (grade, '；'.join(reasons) if reasons else None, priority, survey_id))
    conn.commit()
    conn.close()

    return {'grade': grade, 'reasons': reasons, 'priority': priority}

def create_supervision_task(task_type, priority, title, description='',
                            anonymous_user_id=None, anonymous_code=None,
                            appointment_id=None, followup_survey_id=None,
                            risk_warning_id=None, assigned_to=None, assigned_by=None,
                            deadline_hours=None):
    from config import (SUPERVISION_URGENT_HOURS, SUPERVISION_HIGH_HOURS, SUPERVISION_NORMAL_HOURS)
    conn = get_conn()
    c = conn.cursor()

    task_no = generate_task_no()

    if deadline_hours is None:
        if priority == 'urgent':
            deadline_hours = SUPERVISION_URGENT_HOURS
        elif priority == 'high':
            deadline_hours = SUPERVISION_HIGH_HOURS
        else:
            deadline_hours = SUPERVISION_NORMAL_HOURS

    deadline = (datetime.now() + timedelta(hours=deadline_hours)).strftime('%Y-%m-%d %H:%M:%S')

    c.execute("""INSERT INTO supervision_tasks
                 (task_no, task_type, priority, title, description,
                  anonymous_user_id, anonymous_code,
                  appointment_id, followup_survey_id, risk_warning_id,
                  assigned_to, assigned_by, status, deadline)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (task_no, task_type, priority, title, description,
               anonymous_user_id, anonymous_code,
               appointment_id, followup_survey_id, risk_warning_id,
               assigned_to, assigned_by, 'pending', deadline))
    task_id = c.lastrowid

    c.execute("""INSERT INTO supervision_task_logs
                 (task_id, operator_id, action_type, remark, old_status, new_status)
                 VALUES (?,?,?,?,?,?)""",
              (task_id, assigned_by, 'create', description, None, 'pending'))

    if assigned_to:
        c.execute("""INSERT INTO notifications (user_id, notification_type, title, content, related_appointment_id)
                     VALUES (?, 'supervision', ?, ?, ?)""",
                  (assigned_to, f'新督办任务：{title}',
                   f'您有一个新的督办任务，请及时处理。任务编号：{task_no}', appointment_id))

    conn.commit()
    conn.close()
    return task_id, task_no

def get_supervision_tasks(filters=None, limit=100):
    conn = get_conn()
    c = conn.cursor()
    query = """SELECT st.*, 
                      u_assign.real_name as assigned_to_name,
                      u_assign.username as assigned_to_username,
                      u_by.real_name as assigned_by_name,
                      a.appointment_no,
                      cou.name as counselor_name
               FROM supervision_tasks st
               LEFT JOIN users u_assign ON st.assigned_to = u_assign.id
               LEFT JOIN users u_by ON st.assigned_by = u_by.id
               LEFT JOIN appointments a ON st.appointment_id = a.id
               LEFT JOIN counselors cou ON a.counselor_id = cou.id
               WHERE 1=1"""
    params = []
    if filters:
        if filters.get('status'):
            query += " AND st.status = ?"
            params.append(filters['status'])
        if filters.get('priority'):
            query += " AND st.priority = ?"
            params.append(filters['priority'])
        if filters.get('assigned_to'):
            query += " AND st.assigned_to = ?"
            params.append(filters['assigned_to'])
        if filters.get('task_type'):
            query += " AND st.task_type = ?"
            params.append(filters['task_type'])
        if filters.get('anonymous_code'):
            query += " AND st.anonymous_code LIKE ?"
            params.append(f"%{filters['anonymous_code']}%")
        if filters.get('is_overdue') and filters['is_overdue'] == '1':
            query += " AND st.deadline < ? AND st.status NOT IN ('completed', 'cancelled')"
            params.append(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    query += """ ORDER BY 
                    CASE st.priority 
                        WHEN 'urgent' THEN 1 
                        WHEN 'high' THEN 2 
                        WHEN 'normal' THEN 3 
                        ELSE 4 
                    END,
                    st.deadline ASC,
                    st.created_at DESC
                 LIMIT ?"""
    params.append(limit)
    c.execute(query, params)
    tasks = dict_rows(c.fetchall())

    now = datetime.now()
    for t in tasks:
        if t.get('deadline') and t.get('status') not in ('completed', 'cancelled'):
            try:
                deadline_dt = datetime.strptime(t['deadline'], '%Y-%m-%d %H:%M:%S')
                remaining = deadline_dt - now
                t['remaining_hours'] = round(remaining.total_seconds() / 3600, 1)
                t['is_overdue'] = remaining.total_seconds() < 0
                t['overdue_hours'] = round(abs(remaining.total_seconds()) / 3600, 1) if t['is_overdue'] else 0
            except (ValueError, TypeError):
                t['remaining_hours'] = None
                t['is_overdue'] = False
                t['overdue_hours'] = 0
        else:
            t['remaining_hours'] = None
            t['is_overdue'] = False
            t['overdue_hours'] = 0

        if t.get('anonymous_code') and len(t['anonymous_code']) > 6:
            t['masked_code'] = t['anonymous_code'][:4] + '***' + t['anonymous_code'][-2:]
        else:
            t['masked_code'] = t['anonymous_code'][:3] + '***' if t.get('anonymous_code') else '***'

    conn.close()
    return tasks

def get_supervision_task(task_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT st.*,
                        u_assign.real_name as assigned_to_name,
                        u_assign.username as assigned_to_username,
                        u_by.real_name as assigned_by_name,
                        a.appointment_no, a.appointment_date, a.start_time, a.end_time,
                        cou.name as counselor_name,
                        fs.satisfaction_score, fs.rebook_willingness,
                        rw.risk_level as warning_level
                 FROM supervision_tasks st
                 LEFT JOIN users u_assign ON st.assigned_to = u_assign.id
                 LEFT JOIN users u_by ON st.assigned_by = u_by.id
                 LEFT JOIN appointments a ON st.appointment_id = a.id
                 LEFT JOIN counselors cou ON a.counselor_id = cou.id
                 LEFT JOIN followup_surveys fs ON st.followup_survey_id = fs.id
                 LEFT JOIN risk_warnings rw ON st.risk_warning_id = rw.id
                 WHERE st.id = ?""", (task_id,))
    task = dict_row(c.fetchone())

    if task:
        c.execute("""SELECT stl.*, u.real_name as operator_name
                     FROM supervision_task_logs stl
                     LEFT JOIN users u ON stl.operator_id = u.id
                     WHERE stl.task_id = ?
                     ORDER BY stl.created_at ASC""", (task_id,))
        task['logs'] = dict_rows(c.fetchall())

    conn.close()
    return task

def update_supervision_task_status(task_id, new_status, operator_id=None, remark=''):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM supervision_tasks WHERE id = ?", (task_id,))
    task = dict_row(c.fetchone())
    if not task:
        conn.close()
        return False

    old_status = task['status']
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    updates = ["status = ?", "updated_at = ?"]
    params = [new_status, now, task_id]

    if new_status == 'completed':
        updates.append("completed_at = ?")
        params.insert(-1, now)

    c.execute(f"UPDATE supervision_tasks SET {', '.join(updates)} WHERE id = ?", params)

    c.execute("""INSERT INTO supervision_task_logs
                 (task_id, operator_id, action_type, remark, old_status, new_status)
                 VALUES (?,?,?,?,?,?)""",
              (task_id, operator_id, 'status_change', remark, old_status, new_status))

    if task.get('assigned_to'):
        c.execute("""INSERT INTO notifications (user_id, notification_type, title, content)
                     VALUES (?, 'supervision', ?, ?)""",
                  (task['assigned_to'], f'督办任务状态更新：{task["title"]}',
                   f'任务状态从{old_status}变更为{new_status}。任务编号：{task["task_no"]}'))

    conn.commit()
    conn.close()
    return True

def assign_supervision_task(task_id, assigned_to, assigned_by=None, remark=''):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM supervision_tasks WHERE id = ?", (task_id,))
    task = dict_row(c.fetchone())
    if not task:
        conn.close()
        return False

    old_assignee = task['assigned_to']
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    c.execute("""UPDATE supervision_tasks 
                 SET assigned_to = ?, assigned_by = ?, status = 'in_progress', updated_at = ?
                 WHERE id = ?""",
              (assigned_to, assigned_by, now, task_id))

    c.execute("""INSERT INTO supervision_task_logs
                 (task_id, operator_id, action_type, remark, old_status, new_status)
                 VALUES (?,?,?,?,?,?)""",
              (task_id, assigned_by, 'assign', remark, task['status'], 'in_progress'))

    c.execute("""INSERT INTO notifications (user_id, notification_type, title, content)
                 VALUES (?, 'supervision', ?, ?)""",
              (assigned_to, f'您被指派了新的督办任务',
               f'任务：{task["title"]}\n任务编号：{task["task_no"]}'))

    conn.commit()
    conn.close()
    return True

def get_supervision_summary(user_id=None):
    conn = get_conn()
    c = conn.cursor()

    params = []
    user_clause = ''
    if user_id:
        user_clause = ' AND assigned_to = ?'
        params.append(user_id)

    c.execute(f"""SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                    SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) as in_progress,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) as cancelled,
                    SUM(CASE WHEN priority = 'urgent' AND status NOT IN ('completed','cancelled') THEN 1 ELSE 0 END) as urgent_count,
                    SUM(CASE WHEN priority = 'high' AND status NOT IN ('completed','cancelled') THEN 1 ELSE 0 END) as high_count,
                    SUM(CASE WHEN deadline < ? AND status NOT IN ('completed','cancelled') THEN 1 ELSE 0 END) as overdue
                  FROM supervision_tasks WHERE 1=1{user_clause}""",
              [datetime.now().strftime('%Y-%m-%d %H:%M:%S')] + params)
    summary = dict_row(c.fetchone())
    conn.close()
    
    if summary:
        for key in ['total', 'pending', 'in_progress', 'completed', 'cancelled', 'urgent_count', 'high_count', 'overdue']:
            if summary.get(key) is None:
                summary[key] = 0
    
    return summary if summary else {'total': 0, 'pending': 0, 'in_progress': 0, 'completed': 0, 'cancelled': 0, 'urgent_count': 0, 'high_count': 0, 'overdue': 0}

def create_intervention_archive(anonymous_user_id, anonymous_code, intervention_type,
                                intervention_level=None, intervention_methods=None,
                                intervention_content=None, intervention_effect=None,
                                follow_up_plan=None, appointment_id=None,
                                risk_warning_id=None, supervision_task_id=None,
                                counselor_id=None):
    import json
    conn = get_conn()
    c = conn.cursor()

    archive_no = generate_archive_no()

    methods_json = json.dumps(intervention_methods, ensure_ascii=False) if isinstance(intervention_methods, (list, dict)) else intervention_methods

    c.execute("""INSERT INTO intervention_archives
                 (archive_no, anonymous_user_id, anonymous_code, appointment_id,
                  risk_warning_id, supervision_task_id, counselor_id,
                  intervention_type, intervention_level, intervention_methods,
                  intervention_content, intervention_effect, follow_up_plan)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (archive_no, anonymous_user_id, anonymous_code, appointment_id,
               risk_warning_id, supervision_task_id, counselor_id,
               intervention_type, intervention_level, methods_json,
               intervention_content, intervention_effect, follow_up_plan))
    archive_id = c.lastrowid

    if supervision_task_id:
        c.execute("""UPDATE supervision_tasks 
                     SET status = 'completed', completed_at = ?, updated_at = ?
                     WHERE id = ?""",
                  (datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                   datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                   supervision_task_id))

    conn.commit()
    conn.close()
    return archive_id, archive_no

def get_intervention_archives(filters=None, limit=100):
    import json
    conn = get_conn()
    c = conn.cursor()
    query = """SELECT ia.*, cou.name as counselor_name,
                      a.appointment_no, a.appointment_date
               FROM intervention_archives ia
               LEFT JOIN counselors cou ON ia.counselor_id = cou.id
               LEFT JOIN appointments a ON ia.appointment_id = a.id
               WHERE 1=1"""
    params = []
    if filters:
        if filters.get('is_closed') is not None:
            query += " AND ia.is_closed = ?"
            params.append(filters['is_closed'])
        if filters.get('intervention_type'):
            query += " AND ia.intervention_type = ?"
            params.append(filters['intervention_type'])
        if filters.get('intervention_level'):
            query += " AND ia.intervention_level = ?"
            params.append(filters['intervention_level'])
        if filters.get('anonymous_code'):
            query += " AND ia.anonymous_code LIKE ?"
            params.append(f"%{filters['anonymous_code']}%")
        if filters.get('date_from'):
            query += " AND date(ia.created_at) >= ?"
            params.append(filters['date_from'])
        if filters.get('date_to'):
            query += " AND date(ia.created_at) <= ?"
            params.append(filters['date_to'])
    query += " ORDER BY ia.created_at DESC LIMIT ?"
    params.append(limit)
    c.execute(query, params)
    archives = dict_rows(c.fetchall())

    for a in archives:
        if a.get('intervention_methods'):
            try:
                a['parsed_methods'] = json.loads(a['intervention_methods'])
            except (json.JSONDecodeError, TypeError):
                a['parsed_methods'] = []
        else:
            a['parsed_methods'] = []

        if a.get('anonymous_code') and len(a['anonymous_code']) > 6:
            a['masked_code'] = a['anonymous_code'][:4] + '***' + a['anonymous_code'][-2:]
        else:
            a['masked_code'] = a['anonymous_code'][:3] + '***' if a.get('anonymous_code') else '***'

    conn.close()
    return archives

def get_intervention_archive(archive_id):
    import json
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT ia.*, cou.name as counselor_name,
                        a.appointment_no, a.appointment_date, a.start_time, a.end_time,
                        st.task_no as supervision_task_no,
                        rw.warning_type as risk_warning_type
                 FROM intervention_archives ia
                 LEFT JOIN counselors cou ON ia.counselor_id = cou.id
                 LEFT JOIN appointments a ON ia.appointment_id = a.id
                 LEFT JOIN supervision_tasks st ON ia.supervision_task_id = st.id
                 LEFT JOIN risk_warnings rw ON ia.risk_warning_id = rw.id
                 WHERE ia.id = ?""", (archive_id,))
    archive = dict_row(c.fetchone())

    if archive and archive.get('intervention_methods'):
        try:
            archive['parsed_methods'] = json.loads(archive['intervention_methods'])
        except (json.JSONDecodeError, TypeError):
            archive['parsed_methods'] = []

    conn.close()
    return archive

def close_intervention_archive(archive_id, closed_by, closing_remark=''):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    c.execute("""UPDATE intervention_archives 
                 SET is_closed = 1, closed_by = ?, closed_at = ?, closing_remark = ?, updated_at = ?
                 WHERE id = ?""",
              (closed_by, now, closing_remark, now, archive_id))
    conn.commit()
    conn.close()
    return True

def create_high_risk_tracking(anonymous_user_id, anonymous_code, initial_risk_reason='',
                              assigned_counselor_id=None, assigned_supervisor_id=None):
    from config import HIGH_RISK_FOLLOWUP_INTERVAL_DAYS
    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT id FROM high_risk_tracking WHERE anonymous_user_id = ? AND is_closed = 0", (anonymous_user_id,))
    existing = c.fetchone()
    if existing:
        conn.close()
        return existing['id'], None

    tracking_no = generate_tracking_no()
    next_followup = (date.today() + timedelta(days=HIGH_RISK_FOLLOWUP_INTERVAL_DAYS)).isoformat()

    c.execute("""INSERT INTO high_risk_tracking
                 (tracking_no, anonymous_user_id, anonymous_code, risk_level,
                  initial_risk_reason, current_status, assigned_counselor_id,
                  assigned_supervisor_id, next_followup_date)
                 VALUES (?,?,?,?,?,?,?,?,?)""",
              (tracking_no, anonymous_user_id, anonymous_code, 'high',
               initial_risk_reason, 'monitoring', assigned_counselor_id,
               assigned_supervisor_id, next_followup))
    tracking_id = c.lastrowid

    c.execute("""INSERT INTO high_risk_tracking_logs
                 (tracking_id, operator_id, log_type, content, risk_assessment)
                 VALUES (?,?,?,?,?)""",
              (tracking_id, assigned_supervisor_id, 'init',
               f'建立高风险跟踪台账。原因：{initial_risk_reason}', 'high'))

    conn.commit()
    conn.close()
    return tracking_id, tracking_no

def get_high_risk_trackings(filters=None, limit=100):
    conn = get_conn()
    c = conn.cursor()
    query = """SELECT hrt.*, 
                      cou.name as counselor_name,
                      u.real_name as supervisor_name,
                      au.no_show_count, au.risk_level as user_risk_level
               FROM high_risk_tracking hrt
               LEFT JOIN counselors cou ON hrt.assigned_counselor_id = cou.id
               LEFT JOIN users u ON hrt.assigned_supervisor_id = u.id
               LEFT JOIN anonymous_users au ON hrt.anonymous_user_id = au.id
               WHERE 1=1"""
    params = []
    if filters:
        if filters.get('is_closed') is not None:
            query += " AND hrt.is_closed = ?"
            params.append(filters['is_closed'])
        if filters.get('current_status'):
            query += " AND hrt.current_status = ?"
            params.append(filters['current_status'])
        if filters.get('risk_level'):
            query += " AND hrt.risk_level = ?"
            params.append(filters['risk_level'])
        if filters.get('anonymous_code'):
            query += " AND hrt.anonymous_code LIKE ?"
            params.append(f"%{filters['anonymous_code']}%")
    query += """ ORDER BY 
                    CASE hrt.risk_level 
                        WHEN 'high' THEN 1 
                        WHEN 'medium' THEN 2 
                        ELSE 3 
                    END,
                    hrt.next_followup_date ASC,
                    hrt.created_at DESC
                 LIMIT ?"""
    params.append(limit)
    c.execute(query, params)
    trackings = dict_rows(c.fetchall())

    today = date.today()
    for t in trackings:
        if t.get('anonymous_code') and len(t['anonymous_code']) > 6:
            t['masked_code'] = t['anonymous_code'][:4] + '***' + t['anonymous_code'][-2:]
        else:
            t['masked_code'] = t['anonymous_code'][:3] + '***' if t.get('anonymous_code') else '***'

        if t.get('next_followup_date'):
            try:
                next_dt = datetime.strptime(t['next_followup_date'], '%Y-%m-%d').date()
                days_until = (next_dt - today).days
                t['days_until_followup'] = days_until
                t['is_followup_due'] = days_until <= 0
            except (ValueError, TypeError):
                t['days_until_followup'] = None
                t['is_followup_due'] = False

    conn.close()
    return trackings

def get_high_risk_tracking(tracking_id):
    import json
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT hrt.*,
                        cou.name as counselor_name,
                        u.real_name as supervisor_name,
                        au.no_show_count, au.risk_level as user_risk_level,
                        au.risk_reason as user_risk_reason
                 FROM high_risk_tracking hrt
                 LEFT JOIN counselors cou ON hrt.assigned_counselor_id = cou.id
                 LEFT JOIN users u ON hrt.assigned_supervisor_id = u.id
                 LEFT JOIN anonymous_users au ON hrt.anonymous_user_id = au.id
                 WHERE hrt.id = ?""", (tracking_id,))
    tracking = dict_row(c.fetchone())

    if tracking:
        c.execute("""SELECT hrtl.*, u.real_name as operator_name
                     FROM high_risk_tracking_logs hrtl
                     LEFT JOIN users u ON hrtl.operator_id = u.id
                     WHERE hrtl.tracking_id = ?
                     ORDER BY hrtl.created_at DESC
                     LIMIT 50""", (tracking_id,))
        tracking['logs'] = dict_rows(c.fetchall())

        c.execute("""SELECT COUNT(*) as total_appts,
                            SUM(CASE WHEN checkin_status = 'checked_in' THEN 1 ELSE 0 END) as checked,
                            SUM(CASE WHEN no_show_marked = 1 THEN 1 ELSE 0 END) as noshow
                     FROM appointments 
                     WHERE anonymous_user_id = ?""",
                  (tracking['anonymous_user_id'],))
        appt_stats = dict_row(c.fetchone())
        tracking['appt_stats'] = appt_stats if appt_stats else {'total_appts': 0, 'checked': 0, 'noshow': 0}

        c.execute("""SELECT fs.*, a.appointment_date
                     FROM followup_surveys fs
                     LEFT JOIN appointments a ON fs.appointment_id = a.id
                     WHERE fs.anonymous_user_id = ?
                     ORDER BY fs.created_at DESC
                     LIMIT 10""",
                  (tracking['anonymous_user_id'],))
        tracking['recent_followups'] = dict_rows(c.fetchall())

    conn.close()
    return tracking

def add_high_risk_tracking_log(tracking_id, operator_id, log_type, content='',
                               mood_score=None, risk_assessment=None):
    from config import HIGH_RISK_FOLLOWUP_INTERVAL_DAYS
    conn = get_conn()
    c = conn.cursor()

    c.execute("""INSERT INTO high_risk_tracking_logs
                 (tracking_id, operator_id, log_type, content, mood_score, risk_assessment)
                 VALUES (?,?,?,?,?,?)""",
              (tracking_id, operator_id, log_type, content, mood_score, risk_assessment))

    if log_type == 'followup':
        c.execute("""UPDATE high_risk_tracking 
                     SET followup_count = followup_count + 1,
                         last_followup_date = ?,
                         next_followup_date = ?,
                         updated_at = ?
                     WHERE id = ?""",
                  (date.today().isoformat(),
                   (date.today() + timedelta(days=HIGH_RISK_FOLLOWUP_INTERVAL_DAYS)).isoformat(),
                   datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                   tracking_id))
    else:
        c.execute("UPDATE high_risk_tracking SET updated_at = ? WHERE id = ?",
                  (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), tracking_id))

    conn.commit()
    conn.close()
    return True

def close_high_risk_tracking(tracking_id, closed_by, closing_reason=''):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    c.execute("""UPDATE high_risk_tracking 
                 SET is_closed = 1, current_status = 'closed', closed_by = ?, 
                     closed_at = ?, closing_reason = ?, updated_at = ?
                 WHERE id = ?""",
              (closed_by, now, closing_reason, now, tracking_id))

    c.execute("""INSERT INTO high_risk_tracking_logs
                 (tracking_id, operator_id, log_type, content, risk_assessment)
                 VALUES (?,?,?,?,?)""",
              (tracking_id, closed_by, 'close',
               f'关闭跟踪台账。原因：{closing_reason}', 'low'))

    conn.commit()
    conn.close()
    return True

def get_high_risk_tracking_summary():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN is_closed = 0 AND current_status = 'monitoring' THEN 1 ELSE 0 END) as monitoring,
                    SUM(CASE WHEN is_closed = 0 AND current_status = 'intervening' THEN 1 ELSE 0 END) as intervening,
                    SUM(CASE WHEN is_closed = 1 THEN 1 ELSE 0 END) as closed,
                    SUM(CASE WHEN risk_level = 'high' AND is_closed = 0 THEN 1 ELSE 0 END) as high_risk,
                    SUM(CASE WHEN risk_level = 'medium' AND is_closed = 0 THEN 1 ELSE 0 END) as medium_risk,
                    SUM(CASE WHEN next_followup_date <= ? AND is_closed = 0 THEN 1 ELSE 0 END) as followup_due
                  FROM high_risk_tracking""",
              (date.today().isoformat(),))
    summary = dict_row(c.fetchone())
    conn.close()
    return summary if summary else {}

def get_counselor_quality_comparison(start_date, end_date):
    conn = get_conn()
    c = conn.cursor()

    c.execute("""SELECT 
                    cou.id, cou.name, cou.title, cou.specialty,
                    COUNT(DISTINCT a.id) as total_appointments,
                    COUNT(DISTINCT CASE WHEN a.checkin_status = 'checked_in' THEN a.id END) as attended_appointments,
                    COUNT(DISTINCT fs.id) as followup_count,
                    AVG(fs.satisfaction_score) as avg_satisfaction,
                    SUM(CASE WHEN fs.satisfaction_score = 5 THEN 1 ELSE 0 END) as score_5,
                    SUM(CASE WHEN fs.satisfaction_score = 4 THEN 1 ELSE 0 END) as score_4,
                    SUM(CASE WHEN fs.satisfaction_score = 3 THEN 1 ELSE 0 END) as score_3,
                    SUM(CASE WHEN fs.satisfaction_score = 2 THEN 1 ELSE 0 END) as score_2,
                    SUM(CASE WHEN fs.satisfaction_score = 1 THEN 1 ELSE 0 END) as score_1,
                    SUM(CASE WHEN fs.rebook_willingness = 'yes' THEN 1 ELSE 0 END) as rebook_yes,
                    SUM(CASE WHEN fs.is_abnormal = 1 THEN 1 ELSE 0 END) as abnormal_count,
                    SUM(CASE WHEN fs.is_high_risk = 1 THEN 1 ELSE 0 END) as high_risk_count,
                    COUNT(DISTINCT a.anonymous_user_id) as unique_clients
                 FROM counselors cou
                 LEFT JOIN appointments a ON cou.id = a.counselor_id
                    AND date(a.appointment_date) BETWEEN ? AND ?
                    AND a.checkin_status != 'cancelled'
                 LEFT JOIN followup_surveys fs ON a.id = fs.appointment_id
                 WHERE cou.is_active = 1
                 GROUP BY cou.id
                 ORDER BY avg_satisfaction DESC NULLS LAST, total_appointments DESC""",
              (start_date, end_date))
    counselors = dict_rows(c.fetchall())

    for c_item in counselors:
        total_appts = c_item['total_appointments'] or 0
        attended = c_item['attended_appointments'] or 0
        followups = c_item['followup_count'] or 0
        
        c_item['counselor_name'] = c_item.get('name') or '未知'
        c_item['total_sessions'] = total_appts

        c_item['attendance_rate'] = round(attended / total_appts * 100, 1) if total_appts > 0 else 0
        c_item['avg_satisfaction'] = round(c_item['avg_satisfaction'], 2) if c_item.get('avg_satisfaction') else 0
        c_item['satisfaction_rate'] = round((c_item['score_5'] + c_item['score_4']) / followups * 100, 1) if followups > 0 else 0
        c_item['rebook_rate'] = round(c_item['rebook_yes'] / followups * 100, 1) if followups > 0 else 0
        c_item['abnormal_rate'] = round(c_item['abnormal_count'] / followups * 100, 1) if followups > 0 else 0
        c_item['avg_appts_per_client'] = round(total_appts / (c_item['unique_clients'] or 1), 1)

    conn.close()
    return counselors

def get_rebook_analysis(start_date, end_date):
    from config import REBOOK_ANALYSIS_DAYS
    conn = get_conn()
    c = conn.cursor()

    c.execute("""SELECT 
                    COUNT(DISTINCT au.id) as total_anonymous_users,
                    COUNT(DISTINCT a.id) as total_appointments,
                    SUM(CASE WHEN a.checkin_status = 'checked_in' THEN 1 ELSE 0 END) as attended_appointments
                 FROM anonymous_users au
                 LEFT JOIN appointments a ON au.id = a.anonymous_user_id
                    AND date(a.appointment_date) BETWEEN ? AND ?
                    AND a.checkin_status != 'cancelled'
                 WHERE au.created_at <= ?""",
              (start_date, end_date, end_date))
    basic_stats = dict_row(c.fetchone())

    c.execute("""SELECT 
                    COUNT(DISTINCT au.id) as repeat_users,
                    COUNT(*) as repeat_appointments
                 FROM anonymous_users au
                 JOIN appointments a1 ON au.id = a1.anonymous_user_id
                 JOIN appointments a2 ON au.id = a2.anonymous_user_id AND a2.id > a1.id
                 WHERE date(a1.appointment_date) BETWEEN ? AND ?
                   AND date(a2.appointment_date) BETWEEN ? AND ?
                   AND a1.checkin_status = 'checked_in'
                   AND a2.checkin_status != 'cancelled'""",
              (start_date, end_date, start_date, end_date))
    repeat_stats = dict_row(c.fetchone())

    c.execute("""SELECT cou.id, cou.name,
                    COUNT(DISTINCT au.id) as total_clients,
                    COUNT(DISTINCT CASE WHEN EXISTS (
                        SELECT 1 FROM appointments a2 
                        WHERE a2.anonymous_user_id = au.id 
                        AND a2.counselor_id = cou.id
                        AND a2.id > a1.id
                        AND date(a2.appointment_date) BETWEEN ? AND ?
                        AND a2.checkin_status != 'cancelled'
                    ) THEN au.id END) as returning_clients,
                    COUNT(DISTINCT CASE WHEN EXISTS (
                        SELECT 1 FROM appointments a2 
                        WHERE a2.anonymous_user_id = au.id 
                        AND a2.counselor_id != cou.id
                        AND a2.id > a1.id
                        AND date(a2.appointment_date) BETWEEN ? AND ?
                        AND a2.checkin_status != 'cancelled'
                    ) THEN au.id END) as transferred_clients
                 FROM counselors cou
                 JOIN appointments a1 ON cou.id = a1.counselor_id
                 JOIN anonymous_users au ON a1.anonymous_user_id = au.id
                 WHERE date(a1.appointment_date) BETWEEN ? AND ?
                   AND a1.checkin_status = 'checked_in'
                   AND cou.is_active = 1
                 GROUP BY cou.id
                 ORDER BY returning_clients DESC""",
              (start_date, end_date, start_date, end_date, start_date, end_date))
    counselor_rebook = dict_rows(c.fetchall())

    for cr in counselor_rebook:
        total = cr['total_clients'] or 0
        cr['return_rate'] = round(cr['returning_clients'] / total * 100, 1) if total > 0 else 0
        cr['transfer_rate'] = round(cr['transferred_clients'] / total * 100, 1) if total > 0 else 0

    total_users = basic_stats.get('total_anonymous_users', 0) if basic_stats else 0
    repeat_users = repeat_stats.get('repeat_users', 0) if repeat_stats else 0
    rebook_rate = round(repeat_users / total_users * 100, 1) if total_users > 0 else 0

    c.execute("""SELECT 
                    CAST((julianday(a2.appointment_date) - julianday(a1.appointment_date)) AS INTEGER) as days_diff,
                    COUNT(*) as count
                 FROM appointments a1
                 JOIN appointments a2 ON a1.anonymous_user_id = a2.anonymous_user_id 
                    AND a2.id > a1.id
                 WHERE date(a1.appointment_date) BETWEEN ? AND ?
                   AND date(a2.appointment_date) BETWEEN ? AND ?
                   AND a1.checkin_status = 'checked_in'
                   AND a2.checkin_status != 'cancelled'
                 GROUP BY days_diff
                 ORDER BY days_diff
                 LIMIT 30""",
              (start_date, end_date, start_date, end_date))
    interval_dist = dict_rows(c.fetchall())

    avg_days = 0
    total_intervals = sum(d['count'] for d in interval_dist)
    if total_intervals > 0:
        weighted_sum = sum(d['days_diff'] * d['count'] for d in interval_dist)
        avg_days = round(weighted_sum / total_intervals, 1)

    c.execute("""SELECT 
                    strftime('%Y-%m', a1.appointment_date) as month,
                    COUNT(DISTINCT a1.anonymous_user_id) as new_clients,
                    COUNT(DISTINCT CASE WHEN EXISTS (
                        SELECT 1 FROM appointments a2 
                        WHERE a2.anonymous_user_id = a1.anonymous_user_id 
                        AND a2.appointment_date < a1.appointment_date
                        AND a2.checkin_status != 'cancelled'
                    ) THEN a1.anonymous_user_id END) as returning_clients
                 FROM appointments a1
                 WHERE date(a1.appointment_date) BETWEEN ? AND ?
                   AND a1.checkin_status = 'checked_in'
                 GROUP BY month
                 ORDER BY month""",
              (start_date, end_date))
    monthly_trend = dict_rows(c.fetchall())

    for m in monthly_trend:
        total = m['new_clients'] + m['returning_clients']
        m['new_ratio'] = round(m['new_clients'] / total * 100, 1) if total > 0 else 0
        m['return_ratio'] = round(m['returning_clients'] / total * 100, 1) if total > 0 else 0

    conn.close()

    return {
        'total_users': total_users,
        'repeat_users': repeat_users,
        'rebook_rate': rebook_rate,
        'total_appointments': basic_stats.get('total_appointments', 0) if basic_stats else 0,
        'attended_appointments': basic_stats.get('attended_appointments', 0) if basic_stats else 0,
        'counselor_rebook': counselor_rebook,
        'interval_distribution': interval_dist,
        'avg_interval_days': avg_days,
        'monthly_trend': monthly_trend,
    }

def check_create_followup_supervision(survey_id):
    grade_result = grade_followup_abnormal(survey_id)
    if not grade_result or grade_result['grade'] == 'normal':
        return None

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM followup_surveys WHERE id = ?", (survey_id,))
    survey = dict_row(c.fetchone())
    conn.close()

    if not survey:
        return None

    task_type = 'followup_' + grade_result['grade']
    title = f'回访异常{grade_result["grade"] == "critical" and "紧急" or grade_result["grade"] == "important" and "重要" or "一般"}处理'
    description = '；'.join(grade_result['reasons'])

    task_id, task_no = create_supervision_task(
        task_type=task_type,
        priority=grade_result['priority'],
        title=title,
        description=description,
        anonymous_user_id=survey.get('anonymous_user_id'),
        anonymous_code=survey.get('anonymous_code'),
        appointment_id=survey.get('appointment_id'),
        followup_survey_id=survey_id,
    )

    return task_id, task_no

def check_deadline_reminders():
    from config import SUPERVISION_REMINDER_INTERVAL_HOURS
    conn = get_conn()
    c = conn.cursor()

    now = datetime.now()
    upcoming_deadline = (now + timedelta(hours=SUPERVISION_REMINDER_INTERVAL_HOURS)).strftime('%Y-%m-%d %H:%M:%S')

    c.execute("""SELECT st.*, u.real_name as assignee_name
                 FROM supervision_tasks st
                 JOIN users u ON st.assigned_to = u.id
                 WHERE st.status IN ('pending', 'in_progress')
                   AND st.assigned_to IS NOT NULL
                   AND st.deadline <= ?
                   AND st.last_reminder_sent IS NULL 
                    OR (st.last_reminder_sent IS NOT NULL 
                        AND (strftime('%s', ?) - strftime('%s', st.last_reminder_sent)) / 3600 >= ?)""",
              (upcoming_deadline, now.strftime('%Y-%m-%d %H:%M:%S'), SUPERVISION_REMINDER_INTERVAL_HOURS))

    tasks = dict_rows(c.fetchall())

    for task in tasks:
        is_overdue = task['deadline'] and task['deadline'] < now.strftime('%Y-%m-%d %H:%M:%S')
        title = is_overdue and f'督办任务已超时：{task["title"]}' or f'督办任务即将到期：{task["title"]}'
        content = f'任务编号：{task["task_no"]}\n' + (is_overdue and f'已超时，请尽快处理！' or f'即将在{SUPERVISION_REMINDER_INTERVAL_HOURS}小时内到期，请及时处理。')

        c.execute("""INSERT INTO notifications (user_id, notification_type, title, content)
                     VALUES (?, 'deadline_reminder', ?, ?)""",
                  (task['assigned_to'], title, content))

        c.execute("UPDATE supervision_tasks SET last_reminder_sent = ? WHERE id = ?",
                  (now.strftime('%Y-%m-%d %H:%M:%S'), task['id']))

    conn.commit()
    conn.close()
    return len(tasks)

def get_quality_overview(start_date, end_date):
    conn = get_conn()
    c = conn.cursor()

    c.execute("""SELECT 
                    COUNT(*) as total_surveys,
                    AVG(satisfaction_score) as avg_satisfaction,
                    SUM(CASE WHEN satisfaction_score >= 4 THEN 1 ELSE 0 END) as satisfied,
                    SUM(CASE WHEN is_abnormal = 1 THEN 1 ELSE 0 END) as abnormal,
                    SUM(CASE WHEN is_high_risk = 1 THEN 1 ELSE 0 END) as high_risk,
                    SUM(CASE WHEN rebook_willingness = 'yes' THEN 1 ELSE 0 END) as rebook_yes
                 FROM followup_surveys
                 WHERE date(created_at) BETWEEN ? AND ?""",
              (start_date, end_date))
    followup_stats = dict_row(c.fetchone())

    c.execute("""SELECT 
                    COUNT(*) as total_tasks,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN status = 'completed' AND completed_at <= deadline THEN 1 ELSE 0 END) as on_time,
                    AVG(CASE WHEN status = 'completed' 
                        THEN (julianday(completed_at) - julianday(created_at)) * 24 
                        ELSE NULL END) as avg_completion_hours
                 FROM supervision_tasks
                 WHERE date(created_at) BETWEEN ? AND ?""",
              (start_date, end_date))
    supervision_stats = dict_row(c.fetchone())

    c.execute("""SELECT 
                    COUNT(*) as total_archives,
                    SUM(CASE WHEN is_closed = 1 THEN 1 ELSE 0 END) as closed
                 FROM intervention_archives
                 WHERE date(created_at) BETWEEN ? AND ?""",
              (start_date, end_date))
    archive_stats = dict_row(c.fetchone())

    c.execute("""SELECT 
                    COUNT(*) as total_trackings,
                    SUM(CASE WHEN is_closed = 0 THEN 1 ELSE 0 END) as active,
                    SUM(CASE WHEN is_closed = 1 THEN 1 ELSE 0 END) as closed
                 FROM high_risk_tracking
                 WHERE date(created_at) BETWEEN ? AND ?""",
              (start_date, end_date))
    tracking_stats = dict_row(c.fetchone())

    conn.close()

    total_surveys = followup_stats.get('total_surveys', 0) if followup_stats else 0
    total_tasks = supervision_stats.get('total_tasks', 0) if supervision_stats else 0
    completed_tasks = supervision_stats.get('completed') if supervision_stats else None
    on_time_tasks = supervision_stats.get('on_time') if supervision_stats else None
    
    if total_surveys is None: total_surveys = 0
    if total_tasks is None: total_tasks = 0
    if completed_tasks is None: completed_tasks = 0
    if on_time_tasks is None: on_time_tasks = 0
    
    avg_satisfaction = followup_stats.get('avg_satisfaction') if followup_stats else None
    if avg_satisfaction is None: avg_satisfaction = 0
    
    satisfied = followup_stats.get('satisfied') if followup_stats else 0
    if satisfied is None: satisfied = 0
    
    abnormal = followup_stats.get('abnormal') if followup_stats else 0
    if abnormal is None: abnormal = 0
    
    high_risk = followup_stats.get('high_risk') if followup_stats else 0
    if high_risk is None: high_risk = 0
    
    rebook_yes = followup_stats.get('rebook_yes') if followup_stats else 0
    if rebook_yes is None: rebook_yes = 0
    
    avg_completion_hours = supervision_stats.get('avg_completion_hours') if supervision_stats else None
    if avg_completion_hours is None: avg_completion_hours = 0

    return {
        'total_appointments': total_surveys,
        'avg_satisfaction': round(avg_satisfaction, 2),
        'rebook_rate': round(rebook_yes / total_surveys * 100, 1) if total_surveys > 0 else 0,
        'followup': {
            'total': total_surveys,
            'avg_satisfaction': round(avg_satisfaction, 2),
            'satisfaction_rate': round(satisfied / total_surveys * 100, 1) if total_surveys > 0 else 0,
            'abnormal_rate': round(abnormal / total_surveys * 100, 1) if total_surveys > 0 else 0,
            'high_risk_rate': round(high_risk / total_surveys * 100, 1) if total_surveys > 0 else 0,
            'rebook_rate': round(rebook_yes / total_surveys * 100, 1) if total_surveys > 0 else 0,
        },
        'supervision': {
            'total': total_tasks,
            'completed': completed_tasks,
            'completion_rate': round(completed_tasks / total_tasks * 100, 1) if total_tasks > 0 else 0,
            'on_time_rate': round(on_time_tasks / completed_tasks * 100, 1) if completed_tasks > 0 else 0,
            'avg_completion_hours': round(avg_completion_hours, 1),
        },
        'archives': {
            'total': archive_stats.get('total', 0) if archive_stats else 0,
            'closed': archive_stats.get('closed', 0) if archive_stats else 0,
            'close_rate': round((archive_stats.get('closed') or 0) / (archive_stats.get('total') or 1) * 100, 1),
        },
        'tracking': {
            'total': tracking_stats.get('total', 0) if tracking_stats else 0,
            'active': tracking_stats.get('active', 0) if tracking_stats else 0,
            'closed': tracking_stats.get('closed', 0) if tracking_stats else 0,
        }
    }
