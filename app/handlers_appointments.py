import falcon
import re
from datetime import datetime, date, timedelta
from app.templates import render_template
from app.database import (get_conn, dict_rows, dict_row, generate_appointment_no,
                          create_or_get_anonymous_user, is_in_cooldown,
                          check_concurrent_appointment, check_time_overlap)
from config import CHECKIN_WINDOW_MINUTES_BEFORE, CHECKIN_WINDOW_MINUTES_AFTER, NO_SHOW_THRESHOLD, COOLDOWN_DAYS

class AnonymousBookPage:
    def on_get(self, req, resp):
        target_date = req.get_param('date') or date.today().isoformat()
        try:
            datetime.strptime(target_date, '%Y-%m-%d')
        except ValueError:
            target_date = date.today().isoformat()
        conn = get_conn()
        c = conn.cursor()
        c.execute("""SELECT s.*, cou.name as counselor_name, cou.title as counselor_title,
                            cou.specialty as counselor_specialty, r.room_number, r.room_type, r.privacy_level
                     FROM schedules s
                     JOIN counselors cou ON s.counselor_id = cou.id
                     JOIN rooms r ON s.room_id = r.id
                     WHERE s.schedule_date = ? AND s.status = 'active'
                     AND r.status = 'available' AND cou.is_active = 1
                     ORDER BY s.start_time""", (target_date,))
        schedules = dict_rows(c.fetchall())
        for s in schedules:
            c.execute("""SELECT COUNT(*) as cnt FROM appointments 
                         WHERE schedule_id = ? AND checkin_status != 'cancelled' AND no_show_marked = 0""", (s['id'],))
            s['booked'] = c.fetchone()['cnt']
            s['available'] = max(0, s['capacity'] - s['booked'])
        conn.close()

        resp.content_type = 'text/html; charset=utf-8'
        resp.text = render_template('anonymous_book.html', {
            'target_date': target_date,
            'schedules': schedules,
            'threshold': NO_SHOW_THRESHOLD,
            'cooldown_days': COOLDOWN_DAYS,
            'year': datetime.now().year,
        })

class AnonymousBookCheck:
    def on_post(self, req, resp):
        form = req.get_media() or {}
        anonymous_code = (form.get('anonymous_code') or '').strip()
        schedule_id = form.get('schedule_id')
        target_date = (form.get('target_date') or '').strip()
        if not re.match(r'^[A-Za-z0-9_-]{4,32}$', anonymous_code):
            resp.status = falcon.HTTP_400
            resp.media = {'error': '匿名识别码格式不正确，需4-32位字母数字下划线'}
            return
        conn = get_conn()
        c = conn.cursor()
        c.execute("""SELECT s.*, r.room_number, cou.name as counselor_name 
                     FROM schedules s JOIN rooms r ON s.room_id = r.id
                     JOIN counselors cou ON s.counselor_id = cou.id
                     WHERE s.id = ?""", (schedule_id,))
        sched = dict_row(c.fetchone())
        conn.close()
        if not sched:
            resp.status = falcon.HTTP_400
            resp.media = {'error': '排班不存在'}
            return
        cd_flag, cd_until = is_in_cooldown(anonymous_code, datetime.strptime(target_date, '%Y-%m-%d').date())
        if cd_flag:
            resp.status = falcon.HTTP_400
            resp.media = {'error': f'您正处于冷静期，至{cd_until}后方可预约'}
            return
        conflict = check_concurrent_appointment(anonymous_code, target_date, sched['start_time'], sched['end_time'])
        if conflict:
            resp.status = falcon.HTTP_400
            resp.media = {'error': f'同时段已有预约：{conflict["counselor_name"]} {conflict["start_time"]}-{conflict["end_time"]} ({conflict["room_number"]})'}
            return
        resp.media = {
            'ok': True,
            'schedule': {
                'id': sched['id'],
                'counselor_name': sched['counselor_name'],
                'room_number': sched['room_number'],
                'start_time': sched['start_time'],
                'end_time': sched['end_time'],
                'date': target_date,
            }
        }

class AnonymousBookSubmit:
    def on_post(self, req, resp):
        form = req.get_media() or {}
        anonymous_code = (form.get('anonymous_code') or '').strip()
        schedule_id = form.get('schedule_id')
        target_date = (form.get('target_date') or '').strip()
        if not re.match(r'^[A-Za-z0-9_-]{4,32}$', anonymous_code):
            resp.status = falcon.HTTP_400
            resp.media = {'error': '匿名识别码格式不正确'}
            return
        cd_flag, cd_until = is_in_cooldown(anonymous_code, datetime.strptime(target_date, '%Y-%m-%d').date())
        if cd_flag:
            resp.status = falcon.HTTP_400
            resp.media = {'error': f'冷静期内（至{cd_until}）不能预约'}
            return
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,))
        sched = dict_row(c.fetchone())
        if not sched:
            conn.close()
            resp.status = falcon.HTTP_400
            resp.media = {'error': '排班不存在'}
            return
        conflict = check_concurrent_appointment(anonymous_code, target_date, sched['start_time'], sched['end_time'])
        if conflict:
            conn.close()
            resp.status = falcon.HTTP_400
            resp.media = {'error': '同时段已有有效预约'}
            return
        au = create_or_get_anonymous_user(anonymous_code)
        apt_no = generate_appointment_no()
        try:
            c.execute("""INSERT INTO appointments 
                (appointment_no, anonymous_code, anonymous_user_id, counselor_id, room_id,
                 schedule_id, appointment_date, start_time, end_time)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (apt_no, anonymous_code, au['id'], sched['counselor_id'], sched['room_id'],
                 sched['id'], target_date, sched['start_time'], sched['end_time']))
            conn.commit()
        except Exception as e:
            conn.close()
            resp.status = falcon.HTTP_400
            resp.media = {'error': str(e)}
            return
        c.execute("""SELECT a.*, r.room_number, cou.name as counselor_name 
                     FROM appointments a JOIN rooms r ON a.room_id = r.id
                     JOIN counselors cou ON a.counselor_id = cou.id
                     WHERE a.appointment_no = ?""", (apt_no,))
        apt = dict_row(c.fetchone())
        conn.close()
        resp.content_type = 'text/html; charset=utf-8'
        resp.text = render_template('_book_success.html', {'appointment': apt})

class AppointmentsPage:
    def on_get(self, req, resp):
        user = req.context.user
        today = date.today().isoformat()
        filter_date = req.get_param('date') or today
        status = req.get_param('status') or 'all'
        q = req.get_param('q') or ''
        conn = get_conn()
        c = conn.cursor()
        query = """SELECT a.*, r.room_number, r.room_type, cou.name as counselor_name
                   FROM appointments a
                   JOIN rooms r ON a.room_id = r.id
                   JOIN counselors cou ON a.counselor_id = cou.id
                   WHERE a.appointment_date = ?"""
        params = [filter_date]
        if status == 'pending':
            query += " AND a.checkin_status = 'pending' AND a.no_show_marked = 0"
        elif status == 'checked':
            query += " AND a.checkin_status = 'checked_in'"
        elif status == 'noshow':
            query += " AND a.no_show_marked = 1"
        elif status == 'cancelled':
            query += " AND a.checkin_status = 'cancelled'"
        if q:
            query += " AND (a.anonymous_code LIKE ? OR a.appointment_no LIKE ? OR cou.name LIKE ?)"
            like = f'%{q}%'
            params.extend([like, like, like])
        query += " ORDER BY a.start_time"
        c.execute(query, params)
        appts = dict_rows(c.fetchall())
        for apt in appts:
            apt_dt_str = f"{apt['appointment_date']} {apt['start_time']}"
            try:
                apt_dt = datetime.strptime(apt_dt_str, '%Y-%m-%d %H:%M')
                now = datetime.now()
                before = apt_dt - timedelta(minutes=CHECKIN_WINDOW_MINUTES_BEFORE)
                after = apt_dt + timedelta(minutes=CHECKIN_WINDOW_MINUTES_AFTER)
                apt['can_checkin'] = (apt['checkin_status'] == 'pending' and apt['no_show_marked'] == 0
                                      and before <= now <= after)
                apt['can_mark_noshow'] = (apt['checkin_status'] == 'pending' and apt['no_show_marked'] == 0
                                          and now > after)
            except Exception:
                apt['can_checkin'] = False
                apt['can_mark_noshow'] = False
        conn.close()
        resp.content_type = 'text/html; charset=utf-8'
        resp.text = render_template('appointments.html', {
            'user': user,
            'appointments': appts,
            'filter_date': filter_date,
            'status': status,
            'q': q,
            'nav': 'appointments',
            'before_minutes': CHECKIN_WINDOW_MINUTES_BEFORE,
            'after_minutes': CHECKIN_WINDOW_MINUTES_AFTER,
            'year': datetime.now().year,
        })
