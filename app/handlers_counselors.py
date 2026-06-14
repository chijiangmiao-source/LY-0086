import falcon
from datetime import datetime, date, timedelta
from app.templates import render_template
from app.database import get_conn, dict_rows, dict_row

class CounselorsPage:
    def on_get(self, req, resp):
        user = req.context.user
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM counselors ORDER BY is_active DESC, name")
        counselors = dict_rows(c.fetchall())
        c.execute("SELECT * FROM rooms WHERE status = 'available' ORDER BY room_number")
        rooms = dict_rows(c.fetchall())
        conn.close()
        resp.content_type = 'text/html; charset=utf-8'
        resp.text = render_template('counselors.html', {
            'user': user,
            'counselors': counselors,
            'rooms': rooms,
            'nav': 'counselors',
            'year': datetime.now().year,
        })

class CounselorApi:
    def on_post(self, req, resp):
        form = req.get_media() or {}
        name = (form.get('name') or '').strip()
        if not name:
            resp.status = falcon.HTTP_400
            resp.media = {'error': '姓名必填'}
            return
        conn = get_conn()
        c = conn.cursor()
        c.execute("""INSERT INTO counselors (name, title, specialty, phone, email, is_active)
                     VALUES (?,?,?,?,?,1)""",
                  (name, form.get('title') or '', form.get('specialty') or '',
                   form.get('phone') or '', form.get('email') or ''))
        conn.commit()
        conn.close()
        resp.media = {'success': True, 'id': c.lastrowid}

    def on_put(self, req, resp, counselor_id):
        form = req.get_media() or {}
        conn = get_conn()
        c = conn.cursor()
        updates = []
        params = []
        for field in ['name', 'title', 'specialty', 'phone', 'email', 'is_active']:
            if field in form:
                updates.append(f"{field} = ?")
                val = form[field]
                if field == 'is_active':
                    val = 1 if val in (1, '1', True, 'true') else 0
                params.append(val)
        if updates:
            params.append(counselor_id)
            c.execute(f"UPDATE counselors SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
        conn.close()
        resp.media = {'success': True}

    def on_delete(self, req, resp, counselor_id):
        conn = get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM counselors WHERE id = ?", (counselor_id,))
        conn.commit()
        conn.close()
        resp.media = {'success': True}

class SchedulesPage:
    def on_get(self, req, resp):
        user = req.context.user
        week_offset = int(req.get_param('week') or 0)
        today = date.today()
        monday = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
        week_dates = [(monday + timedelta(days=i)).isoformat() for i in range(7)]
        week_labels = [(monday + timedelta(days=i)).strftime('%m-%d 周%w').replace('周0', '周日').replace('周1', '周一').replace('周2', '周二').replace('周3', '周三').replace('周4', '周四').replace('周5', '周五').replace('周6', '周六') for i in range(7)]
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM counselors WHERE is_active = 1 ORDER BY name")
        counselors = dict_rows(c.fetchall())
        c.execute("SELECT * FROM rooms ORDER BY room_number")
        rooms = dict_rows(c.fetchall())
        placeholders = ','.join(['?'] * 7)
        c.execute(f"""SELECT s.*, cou.name as counselor_name, r.room_number 
                      FROM schedules s 
                      JOIN counselors cou ON s.counselor_id = cou.id
                      JOIN rooms r ON s.room_id = r.id
                      WHERE s.schedule_date IN ({placeholders})
                      ORDER BY s.schedule_date, s.start_time""", week_dates)
        schedules = dict_rows(c.fetchall())
        conn.close()
        schedule_map = {}
        for s in schedules:
            key = (s['counselor_id'], s['schedule_date'])
            schedule_map.setdefault(key, []).append(s)
        resp.content_type = 'text/html; charset=utf-8'
        resp.text = render_template('schedules.html', {
            'user': user,
            'counselors': counselors,
            'rooms': rooms,
            'week_dates': week_dates,
            'week_labels': week_labels,
            'schedule_map': schedule_map,
            'week_offset': week_offset,
            'nav': 'schedules',
            'year': datetime.now().year,
        })

class ScheduleApi:
    def on_post(self, req, resp):
        form = req.get_media() or {}
        counselor_id = form.get('counselor_id')
        room_id = form.get('room_id')
        schedule_date = (form.get('schedule_date') or '').strip()
        start_time = (form.get('start_time') or '').strip()
        end_time = (form.get('end_time') or '').strip()
        if not all([counselor_id, room_id, schedule_date, start_time, end_time]):
            resp.status = falcon.HTTP_400
            resp.media = {'error': '所有字段必填'}
            return
        conn = get_conn()
        c = conn.cursor()
        try:
            c.execute("""INSERT INTO schedules (counselor_id, room_id, schedule_date, start_time, end_time)
                         VALUES (?,?,?,?,?)""", (counselor_id, room_id, schedule_date, start_time, end_time))
            conn.commit()
        except Exception as e:
            conn.close()
            resp.status = falcon.HTTP_400
            resp.media = {'error': str(e)}
            return
        conn.close()
        resp.media = {'success': True}

    def on_delete(self, req, resp, schedule_id):
        conn = get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
        conn.commit()
        conn.close()
        resp.media = {'success': True}
