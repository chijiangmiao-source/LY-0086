import falcon
from datetime import datetime, timedelta, date
from app.templates import render_template
from app.database import (get_conn, dict_rows, dict_row, increment_no_show, lift_cooldown,
                          reset_consecutive_no_show, update_risk_level, create_risk_warning,
                          create_notification, has_permission)
from config import CHECKIN_WINDOW_MINUTES_BEFORE, CHECKIN_WINDOW_MINUTES_AFTER, COOLDOWN_DAYS

def require_permission(req, resp, permission):
    user = req.context.user
    if not user:
        resp.status = falcon.HTTP_401
        resp.media = {'error': '未登录'}
        resp.complete = True
        return False
    if not has_permission(user['role'], permission):
        resp.status = falcon.HTTP_403
        resp.media = {'error': '权限不足'}
        resp.complete = True
        return False
    return True

class CheckinApi:
    def on_post(self, req, resp):
        if not require_permission(req, resp, 'check_in'):
            return
        user = req.context.user
        form = req.get_media() or {}
        apt_id = form.get('appointment_id')
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM appointments WHERE id = ?", (apt_id,))
        apt = dict_row(c.fetchone())
        if not apt:
            conn.close()
            resp.status = falcon.HTTP_404
            resp.media = {'error': '预约不存在'}
            return
        if apt['checkin_status'] == 'checked_in':
            conn.close()
            resp.status = falcon.HTTP_400
            resp.media = {'error': '该预约已签到'}
            return
        if apt['checkin_status'] == 'cancelled':
            conn.close()
            resp.status = falcon.HTTP_400
            resp.media = {'error': '该预约已取消'}
            return
        apt_dt_str = f"{apt['appointment_date']} {apt['start_time']}"
        try:
            apt_dt = datetime.strptime(apt_dt_str, '%Y-%m-%d %H:%M')
        except Exception:
            apt_dt = datetime.now()
        now = datetime.now()
        before = apt_dt - timedelta(minutes=CHECKIN_WINDOW_MINUTES_BEFORE)
        after = apt_dt + timedelta(minutes=CHECKIN_WINDOW_MINUTES_AFTER)
        if now < before:
            diff = int((before - now).total_seconds() // 60)
            conn.close()
            resp.status = falcon.HTTP_400
            resp.media = {'error': f'签到窗口未开启，还需等待{diff}分钟（提前{CHECKIN_WINDOW_MINUTES_BEFORE}分钟可签到）'}
            return
        if now > after:
            diff = int((now - after).total_seconds() // 60)
            conn.close()
            resp.status = falcon.HTTP_400
            resp.media = {'error': f'已错过签到窗口（超过{diff}分钟，超过开始时间{CHECKIN_WINDOW_MINUTES_AFTER}分钟不能签到）'}
            return

        is_late = now > apt_dt
        late_minutes = int((now - apt_dt).total_seconds() // 60) if is_late else 0

        c.execute("UPDATE appointments SET checkin_status = 'checked_in', checkin_time = ? WHERE id = ?",
                  (now.strftime('%Y-%m-%d %H:%M:%S'), apt_id))
        if apt['anonymous_user_id']:
            c.execute("UPDATE anonymous_users SET last_visit_date = ? WHERE id = ?",
                      (date.today().isoformat(), apt['anonymous_user_id']))
            reset_consecutive_no_show(apt['anonymous_user_id'], reason='正常签到履约')
            update_risk_level(apt['anonymous_user_id'])

        if is_late and late_minutes >= 15:
            if apt['anonymous_user_id']:
                c.execute("""INSERT INTO notifications (user_id, notification_type, title, content, related_appointment_id)
                             SELECT u.id, 'checkin_anomaly', ?, ?, ?
                             FROM users u 
                             WHERE u.role IN ('admin', 'intervention', 'staff')""",
                          (f'签到异常：迟到{late_minutes}分钟',
                           f'用户 {apt["anonymous_code"]} 预约 {apt["appointment_no"]} 迟到{late_minutes}分钟签到',
                           apt_id))

        conn.commit()
        conn.close()
        resp.media = {
            'success': True,
            'checkin_time': now.strftime('%H:%M:%S'),
            'is_late': is_late,
            'late_minutes': late_minutes,
        }

class MarkNoShowApi:
    def on_post(self, req, resp):
        if not require_permission(req, resp, 'mark_no_show'):
            return
        user = req.context.user
        form = req.get_media() or {}
        apt_id = form.get('appointment_id')
        remark = (form.get('remark') or '').strip()
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM appointments WHERE id = ?", (apt_id,))
        apt = dict_row(c.fetchone())
        if not apt:
            conn.close()
            resp.status = falcon.HTTP_404
            resp.media = {'error': '预约不存在'}
            return
        if apt['checkin_status'] == 'checked_in':
            conn.close()
            resp.status = falcon.HTTP_400
            resp.media = {'error': '已签到的预约不能标记为失约'}
            return
        if apt['no_show_marked']:
            conn.close()
            resp.status = falcon.HTTP_400
            resp.media = {'error': '该预约已标记为失约'}
            return
        c.execute("UPDATE appointments SET no_show_marked = 1, intervention_status = 'pending' WHERE id = ?", (apt_id,))
        cooldown_until = None
        cooldown_reason = None
        noshow_count = None
        if apt['anonymous_user_id']:
            cooldown_until, cooldown_reason, noshow_count = increment_no_show(apt['anonymous_user_id'], apt['anonymous_code'])
            risk_level, risk_reason = update_risk_level(apt['anonymous_user_id'])
            if risk_level == 'high':
                c.execute("""INSERT INTO risk_warnings 
                    (anonymous_user_id, anonymous_code, warning_type, risk_level, description, appointment_id)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (apt['anonymous_user_id'], apt['anonymous_code'], 'consecutive_noshow', 'high',
                     f'连续失约{noshow_count}次，已触发高风险预警', apt_id))
                c.execute("""INSERT INTO notifications (user_id, notification_type, title, content, related_appointment_id)
                             SELECT u.id, 'risk_warning', ?, ?, ?
                             FROM users u 
                             WHERE u.role IN ('admin', 'intervention')""",
                          (f'高风险预警：连续失约{noshow_count}次',
                           f'用户 {apt["anonymous_code"]} 连续失约{noshow_count}次，已进入冷静期',
                           apt_id))

        c.execute("""INSERT INTO intervention_records 
            (appointment_id, anonymous_user_id, anonymous_code, operator_id, action_type, remark, old_status, new_status)
            VALUES (?,?,?,?,?,?,?,?)""",
            (apt_id, apt['anonymous_user_id'], apt['anonymous_code'], user['user_id'],
             'mark_no_show', remark, apt['intervention_status'] or 'none',
             f'noshow{cooldown_until and f" cooldown_to_{cooldown_until}" or ""}'))
        conn.commit()
        conn.close()
        resp.media = {
            'success': True,
            'cooldown_until': cooldown_until,
            'cooldown_reason': cooldown_reason,
        }

class CancelAppointmentApi:
    def on_post(self, req, resp):
        if not require_permission(req, resp, 'cancel_appointment'):
            return
        user = req.context.user
        form = req.get_media() or {}
        apt_id = form.get('appointment_id')
        reason = (form.get('reason') or '').strip()
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM appointments WHERE id = ?", (apt_id,))
        apt = dict_row(c.fetchone())
        if not apt:
            conn.close()
            resp.status = falcon.HTTP_404
            resp.media = {'error': '预约不存在'}
            return
        if apt['checkin_status'] == 'checked_in':
            conn.close()
            resp.status = falcon.HTTP_400
            resp.media = {'error': '已签到的预约不能取消'}
            return
        c.execute("UPDATE appointments SET checkin_status = 'cancelled' WHERE id = ?", (apt_id,))
        if apt['anonymous_user_id']:
            reset_consecutive_no_show(apt['anonymous_user_id'], reason='主动取消预约')
            update_risk_level(apt['anonymous_user_id'])
        c.execute("""INSERT INTO intervention_records 
            (appointment_id, anonymous_user_id, anonymous_code, operator_id, action_type, remark, old_status, new_status)
            VALUES (?,?,?,?,?,?,?,?)""",
            (apt_id, apt['anonymous_user_id'], apt['anonymous_code'], user['user_id'],
             'cancel', reason, apt['checkin_status'], 'cancelled'))
        conn.commit()
        conn.close()
        resp.media = {'success': True}

class InterventionsPage:
    def on_get(self, req, resp):
        user = req.context.user
        today = date.today().isoformat()
        can_view = has_permission(user['role'], 'view_interventions')
        can_manage = has_permission(user['role'], 'manage_interventions')
        can_lift = has_permission(user['role'], 'lift_cooldown')
        if not can_view:
            resp.status = falcon.HTTP_403
            resp.text = '权限不足'
            return
        conn = get_conn()
        c = conn.cursor()
        c.execute("""SELECT au.*, 
                     (SELECT COUNT(*) FROM appointments a 
                      WHERE a.anonymous_user_id = au.id AND a.no_show_marked = 1 
                      AND date(a.created_at, '-7 days') <= date('now')) as recent_noshow
                     FROM anonymous_users au 
                     WHERE au.cooldown_until >= ?
                     ORDER BY au.cooldown_until DESC""", (today,))
        cooldown_users = dict_rows(c.fetchall())
        c.execute("""SELECT a.*, r.room_number, cou.name as counselor_name, au.risk_level
                     FROM appointments a
                     JOIN rooms r ON a.room_id = r.id
                     JOIN counselors cou ON a.counselor_id = cou.id
                     LEFT JOIN anonymous_users au ON a.anonymous_user_id = au.id
                     WHERE a.no_show_marked = 1 AND a.intervention_status = 'pending'
                     ORDER BY a.appointment_date DESC, a.start_time LIMIT 50""")
        pending_appts = dict_rows(c.fetchall())
        c.execute("""SELECT ir.*, u.real_name as operator_name, a.appointment_no
                     FROM intervention_records ir
                     LEFT JOIN users u ON ir.operator_id = u.id
                     LEFT JOIN appointments a ON ir.appointment_id = a.id
                     ORDER BY ir.created_at DESC LIMIT 100""")
        records = dict_rows(c.fetchall())
        conn.close()
        can_intervene = can_manage or can_lift
        resp.content_type = 'text/html; charset=utf-8'
        resp.text = render_template('interventions.html', {
            'user': user,
            'cooldown_users': cooldown_users,
            'pending_appts': pending_appts,
            'records': records,
            'can_intervene': can_intervene,
            'can_lift': can_lift,
            'can_manage': can_manage,
            'cooldown_days': COOLDOWN_DAYS,
            'nav': 'interventions',
            'year': datetime.now().year,
        })

class LiftCooldownApi:
    def on_post(self, req, resp):
        if not require_permission(req, resp, 'lift_cooldown'):
            return
        user = req.context.user
        form = req.get_media() or {}
        anonymous_user_id = form.get('anonymous_user_id')
        remark = (form.get('remark') or '').strip()
        if not remark:
            resp.status = falcon.HTTP_400
            resp.media = {'error': '请填写解除原因备注'}
            return
        lift_cooldown(anonymous_user_id, user['user_id'], remark)
        update_risk_level(anonymous_user_id)
        resp.media = {'success': True}

class InterventionRemarkApi:
    def on_post(self, req, resp):
        if not require_permission(req, resp, 'manage_interventions'):
            return
        user = req.context.user
        form = req.get_media() or {}
        apt_id = form.get('appointment_id')
        status = form.get('status') or 'contacted'
        remark = (form.get('remark') or '').strip()
        if not remark:
            resp.status = falcon.HTTP_400
            resp.media = {'error': '请填写干预备注'}
            return
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM appointments WHERE id = ?", (apt_id,))
        apt = dict_row(c.fetchone())
        if not apt:
            conn.close()
            resp.status = falcon.HTTP_404
            resp.media = {'error': '预约不存在'}
            return
        old = apt['intervention_status']
        c.execute("UPDATE appointments SET intervention_status = ? WHERE id = ?", (status, apt_id))
        c.execute("""INSERT INTO intervention_records 
            (appointment_id, anonymous_user_id, anonymous_code, operator_id, action_type, remark, old_status, new_status)
            VALUES (?,?,?,?,?,?,?,?)""",
            (apt_id, apt['anonymous_user_id'], apt['anonymous_code'], user['user_id'],
             'remark', remark, old, status))
        conn.commit()
        conn.close()
        resp.media = {'success': True}
