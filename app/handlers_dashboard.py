import falcon
from datetime import datetime, date
from app.templates import render_template
from app.database import get_conn, dict_rows, dict_row
from config import CHECKIN_WINDOW_MINUTES_BEFORE, CHECKIN_WINDOW_MINUTES_AFTER

class Dashboard:
    def on_get(self, req, resp):
        user = req.context.user
        today = date.today().isoformat()
        conn = get_conn()
        c = conn.cursor()

        c.execute("SELECT COUNT(*) as cnt FROM appointments WHERE appointment_date = ?", (today,))
        today_appts = c.fetchone()['cnt']

        c.execute("SELECT COUNT(*) as cnt FROM appointments WHERE appointment_date = ? AND checkin_status = 'checked_in'", (today,))
        today_checked = c.fetchone()['cnt']

        c.execute("SELECT COUNT(*) as cnt FROM anonymous_users WHERE cooldown_until >= ?", (today,))
        cooldown_count = c.fetchone()['cnt']

        c.execute("SELECT COUNT(*) as cnt FROM appointments WHERE no_show_marked = 1 AND date(created_at) = ?", (today,))
        today_noshow = c.fetchone()['cnt']

        c.execute("""SELECT a.*, r.room_number, cou.name as counselor_name 
                     FROM appointments a 
                     JOIN rooms r ON a.room_id = r.id
                     JOIN counselors cou ON a.counselor_id = cou.id
                     WHERE a.appointment_date = ? 
                     ORDER BY a.start_time ASC LIMIT 10""", (today,))
        today_list = dict_rows(c.fetchall())

        c.execute("SELECT COUNT(*) as cnt FROM rooms")
        total_rooms = c.fetchone()['cnt']

        c.execute("SELECT COUNT(*) as cnt FROM counselors WHERE is_active = 1")
        active_counselors = c.fetchone()['cnt']

        c.execute("SELECT COUNT(*) as cnt FROM risk_warnings WHERE is_resolved = 0")
        unresolved_warnings = c.fetchone()['cnt']

        conn.close()

        resp.content_type = 'text/html; charset=utf-8'
        resp.text = render_template('dashboard.html', {
            'user': user,
            'today': today,
            'today_appts': today_appts,
            'today_checked': today_checked,
            'today_noshow': today_noshow,
            'cooldown_count': cooldown_count,
            'total_rooms': total_rooms,
            'active_counselors': active_counselors,
            'today_list': today_list,
            'unresolved_warnings': unresolved_warnings,
            'nav': 'dashboard',
            'year': datetime.now().year,
        })
