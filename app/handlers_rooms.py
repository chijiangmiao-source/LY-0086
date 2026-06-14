import falcon
from datetime import datetime
from app.templates import render_template
from app.database import get_conn, dict_rows, dict_row

class RoomsPage:
    def on_get(self, req, resp):
        user = req.context.user
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM rooms ORDER BY room_number")
        rooms = dict_rows(c.fetchall())
        conn.close()
        resp.content_type = 'text/html; charset=utf-8'
        resp.text = render_template('rooms.html', {
            'user': user,
            'rooms': rooms,
            'nav': 'rooms',
            'year': datetime.now().year,
        })

class RoomFormPartial:
    def on_get(self, req, resp, room_id=None):
        user = req.context.user
        room = None
        if room_id:
            conn = get_conn()
            c = conn.cursor()
            c.execute("SELECT * FROM rooms WHERE id = ?", (room_id,))
            room = dict_row(c.fetchone())
            conn.close()
        resp.content_type = 'text/html; charset=utf-8'
        resp.text = render_template('_room_form.html', {'room': room, 'user': user})

class RoomApi:
    def on_post(self, req, resp):
        user = req.context.user
        form = req.get_media() or {}
        room_number = (form.get('room_number') or '').strip()
        room_type = (form.get('room_type') or '').strip()
        privacy_level = form.get('privacy_level') or 'normal'
        status = form.get('status') or 'available'
        description = (form.get('description') or '').strip()
        if not room_number or not room_type:
            resp.status = falcon.HTTP_400
            resp.media = {'error': '房间编号和类型必填'}
            return
        conn = get_conn()
        c = conn.cursor()
        try:
            c.execute("""INSERT INTO rooms (room_number, room_type, privacy_level, status, description)
                         VALUES (?,?,?,?,?)""", (room_number, room_type, privacy_level, status, description))
            conn.commit()
        except Exception as e:
            conn.close()
            resp.status = falcon.HTTP_400
            resp.media = {'error': str(e)}
            return
        conn.close()
        resp.status = falcon.HTTP_200
        resp.media = {'success': True}

    def on_put(self, req, resp, room_id):
        user = req.context.user
        form = req.get_media() or {}
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM rooms WHERE id = ?", (room_id,))
        if not c.fetchone():
            conn.close()
            resp.status = falcon.HTTP_404
            resp.media = {'error': '房间不存在'}
            return
        updates = []
        params = []
        for field in ['room_number', 'room_type', 'privacy_level', 'status', 'description']:
            if field in form:
                updates.append(f"{field} = ?")
                params.append(form[field])
        params.append(room_id)
        c.execute(f"UPDATE rooms SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
        conn.close()
        resp.media = {'success': True}

    def on_delete(self, req, resp, room_id):
        user = req.context.user
        conn = get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
        conn.commit()
        conn.close()
        resp.media = {'success': True}
