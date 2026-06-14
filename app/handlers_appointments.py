import falcon
import re
from datetime import datetime, date, timedelta
from app.templates import render_template
from app.database import (get_conn, dict_rows, dict_row, generate_appointment_no,
                          create_or_get_anonymous_user, is_in_cooldown,
                          check_concurrent_appointment, check_time_overlap,
                          check_schedule_capacity, check_schedule_capacity_with_lock,
                          check_appointment_counselor_conflict,
                          check_appointment_room_conflict,
                          check_abnormal_booking, create_risk_warning,
                          update_risk_level, get_anonymous_user,
                          calculate_risk_level)
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
            s['is_full'] = s['available'] == 0
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

        au = get_anonymous_user(anonymous_code)
        if au and au.get('risk_level') == 'high':
            resp.status = falcon.HTTP_400
            resp.media = {
                'error': f'您的账号当前处于高风险状态（{au.get("risk_reason", "行为异常")}），请联系工作人员处理'
            }
            return

        capacity_info = check_schedule_capacity(schedule_id)
        if capacity_info is None:
            resp.status = falcon.HTTP_400
            resp.media = {'error': '排班不存在'}
            return
        if capacity_info['full']:
            resp.status = falcon.HTTP_400
            resp.media = {'error': f'该时段已满员（{capacity_info["booked"]}/{capacity_info["capacity"]}）'}
            return
        conflict = check_concurrent_appointment(anonymous_code, target_date, sched['start_time'], sched['end_time'])
        if conflict:
            resp.status = falcon.HTTP_400
            resp.media = {'error': f'同时段已有预约：{conflict["counselor_name"]} {conflict["start_time"]}-{conflict["end_time"]} ({conflict["room_number"]})'}
            return
        counselor_conflict = check_appointment_counselor_conflict(sched['counselor_id'], target_date, sched['start_time'], sched['end_time'])
        if counselor_conflict:
            resp.status = falcon.HTTP_400
            resp.media = {'error': f'咨询师时段冲突：{sched["counselor_name"]} 在 {sched["start_time"]}-{sched["end_time"]} 于 {counselor_conflict["room_number"]} 已有预约'}
            return
        room_conflict = check_appointment_room_conflict(sched['room_id'], target_date, sched['start_time'], sched['end_time'])
        if room_conflict:
            resp.status = falcon.HTTP_400
            resp.media = {'error': f'房间冲突：{sched["room_number"]} 在 {sched["start_time"]}-{sched["end_time"]} 已被 {room_conflict["counselor_name"]} 预约'}
            return

        is_abnormal, abnormal_reasons = check_abnormal_booking(anonymous_code, target_date)
        warning_info = None
        if is_abnormal:
            warning_info = {
                'level': 'warning',
                'message': '检测到您的预约行为存在异常，请谨慎预约，频繁失约将触发冷静期。'
            }

        resp.media = {
            'ok': True,
            'schedule': {
                'id': sched['id'],
                'counselor_name': sched['counselor_name'],
                'room_number': sched['room_number'],
                'start_time': sched['start_time'],
                'end_time': sched['end_time'],
                'date': target_date,
            },
            'warning': warning_info,
            'is_abnormal': is_abnormal,
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

        au_check = get_anonymous_user(anonymous_code)
        if au_check and au_check.get('risk_level') == 'high':
            resp.status = falcon.HTTP_400
            resp.media = {'error': '您的账号处于高风险状态，暂无法预约，请联系工作人员'}
            return

        is_abnormal, abnormal_reasons = check_abnormal_booking(anonymous_code, target_date)

        au = create_or_get_anonymous_user(anonymous_code)

        conn = get_conn()
        conn.execute("BEGIN IMMEDIATE")
        try:
            c = conn.cursor()
            c.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,))
            sched = dict_row(c.fetchone())
            if not sched:
                conn.rollback()
                resp.status = falcon.HTTP_400
                resp.media = {'error': '排班不存在'}
                return

            conflict = check_concurrent_appointment(anonymous_code, target_date, sched['start_time'], sched['end_time'])
            if conflict:
                conn.rollback()
                resp.status = falcon.HTTP_400
                resp.media = {'error': '同时段已有有效预约'}
                return

            capacity_info = check_schedule_capacity_with_lock(schedule_id, conn)
            if capacity_info is None:
                conn.rollback()
                resp.status = falcon.HTTP_400
                resp.media = {'error': '排班不存在'}
                return
            if capacity_info['full']:
                conn.rollback()
                resp.status = falcon.HTTP_400
                resp.media = {'error': f'该时段已满员（{capacity_info["booked"]}/{capacity_info["capacity"]}），请选择其他时段'}
                return

            counselor_conflict = check_appointment_counselor_conflict(sched['counselor_id'], target_date, sched['start_time'], sched['end_time'])
            if counselor_conflict:
                conn.rollback()
                resp.status = falcon.HTTP_400
                resp.media = {'error': f'咨询师时段冲突：{sched["counselor_id"]}号咨询师 于 {sched["start_time"]}-{sched["end_time"]} 在房间 {counselor_conflict["room_number"]} 已有预约'}
                return
            room_conflict = check_appointment_room_conflict(sched['room_id'], target_date, sched['start_time'], sched['end_time'])
            if room_conflict:
                conn.rollback()
                resp.status = falcon.HTTP_400
                resp.media = {'error': f'房间冲突：{sched["room_id"]}号房间 在 {sched["start_time"]}-{sched["end_time"]} 已被 {room_conflict["counselor_name"]} 预约'}
                return

            apt_no = generate_appointment_no()

            is_abnormal_flag = 1 if is_abnormal else 0
            abnormal_reason = '；'.join(abnormal_reasons) if is_abnormal else None

            c.execute("""INSERT INTO appointments 
                (appointment_no, anonymous_code, anonymous_user_id, counselor_id, room_id,
                 schedule_id, appointment_date, start_time, end_time, is_abnormal, abnormal_reason)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (apt_no, anonymous_code, au['id'], sched['counselor_id'], sched['room_id'],
                 sched['id'], target_date, sched['start_time'], sched['end_time'],
                 is_abnormal_flag, abnormal_reason))
            apt_id = c.lastrowid

            if is_abnormal:
                risk_level, risk_reason = calculate_risk_level(au['id'])
                c.execute("""UPDATE anonymous_users 
                             SET risk_level = ?, risk_reason = ?, risk_updated_at = ? 
                             WHERE id = ?""",
                          (risk_level, risk_reason, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), au['id']))
                if risk_level in ('medium', 'high'):
                    c.execute("""INSERT INTO risk_warnings 
                        (anonymous_user_id, anonymous_code, warning_type, risk_level, description, appointment_id)
                        VALUES (?, ?, ?, ?, ?, ?)""",
                        (au['id'], anonymous_code, 'abnormal_booking', risk_level,
                         f'异常预约行为：{abnormal_reason}', apt_id))
                    c.execute("""INSERT INTO notifications (user_id, notification_type, title, content, related_appointment_id)
                                 SELECT u.id, 'risk_warning', ?, ?, ?
                                 FROM users u 
                                 WHERE u.role IN ('admin', 'intervention')""",
                              (f'风险预警：异常预约行为', f'用户 {anonymous_code} 存在异常预约行为：{abnormal_reason}', apt_id))

            conn.commit()

            c.execute("""SELECT a.*, r.room_number, cou.name as counselor_name 
                         FROM appointments a JOIN rooms r ON a.room_id = r.id
                         JOIN counselors cou ON a.counselor_id = cou.id
                         WHERE a.appointment_no = ?""", (apt_no,))
            apt = dict_row(c.fetchone())
            conn.close()

            resp.content_type = 'text/html; charset=utf-8'
            resp.text = render_template('_book_success.html', {
                'appointment': apt,
                'is_abnormal': is_abnormal,
                'abnormal_reasons': abnormal_reasons,
            })

        except Exception as e:
            conn.rollback()
            conn.close()
            resp.status = falcon.HTTP_400
            resp.media = {'error': f'预约失败：{str(e)}'}
            return

class AppointmentsPage:
    def on_get(self, req, resp):
        user = req.context.user
        today = date.today().isoformat()
        filter_date = req.get_param('date') or today
        status = req.get_param('status') or 'all'
        risk_filter = req.get_param('risk') or 'all'
        q = req.get_param('q') or ''
        conn = get_conn()
        c = conn.cursor()
        query = """SELECT a.*, r.room_number, r.room_type, cou.name as counselor_name, au.risk_level
                   FROM appointments a
                   JOIN rooms r ON a.room_id = r.id
                   JOIN counselors cou ON a.counselor_id = cou.id
                   LEFT JOIN anonymous_users au ON a.anonymous_user_id = au.id
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
        elif status == 'abnormal':
            query += " AND a.is_abnormal = 1"
        if risk_filter != 'all':
            query += " AND au.risk_level = ?"
            params.append(risk_filter)
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
                if apt['checkin_status'] == 'checked_in' and apt.get('checkin_time'):
                    checkin_dt = datetime.strptime(apt['checkin_time'], '%Y-%m-%d %H:%M:%S')
                    late_delta = checkin_dt - apt_dt
                    late_minutes = int(late_delta.total_seconds() / 60)
                    apt['is_late'] = late_minutes > 0
                    apt['late_minutes'] = max(0, late_minutes)
                else:
                    apt['is_late'] = (apt['checkin_status'] == 'pending' and apt['no_show_marked'] == 0
                                      and now > apt_dt)
                    apt['late_minutes'] = 0
            except Exception:
                apt['can_checkin'] = False
                apt['can_mark_noshow'] = False
                apt['is_late'] = False
                apt['late_minutes'] = 0
        conn.close()
        resp.content_type = 'text/html; charset=utf-8'
        resp.text = render_template('appointments.html', {
            'user': user,
            'appointments': appts,
            'filter_date': filter_date,
            'status': status,
            'risk_filter': risk_filter,
            'q': q,
            'nav': 'appointments',
            'before_minutes': CHECKIN_WINDOW_MINUTES_BEFORE,
            'after_minutes': CHECKIN_WINDOW_MINUTES_AFTER,
            'year': datetime.now().year,
        })
