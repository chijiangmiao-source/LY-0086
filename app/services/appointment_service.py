import re
from datetime import datetime, date, timedelta
from app.database import (
    get_conn, dict_rows, dict_row, generate_appointment_no,
    create_or_get_anonymous_user, is_in_cooldown,
    check_concurrent_appointment, check_time_overlap,
    check_schedule_capacity, check_schedule_capacity_with_lock,
    check_appointment_counselor_conflict,
    check_appointment_room_conflict,
    check_abnormal_booking, create_risk_warning,
    update_risk_level, get_anonymous_user,
    calculate_risk_level,
)
from app.utils.validators import validate_anonymous_code, validate_date_str
from app.utils.exceptions import ValidationError, BusinessError, ConflictError
from app.services.notification_service import NotificationService
from app.utils.helpers import now_str
from config import CHECKIN_WINDOW_MINUTES_BEFORE, CHECKIN_WINDOW_MINUTES_AFTER


class AppointmentService:

    @staticmethod
    def get_schedules_for_date(target_date):
        ok, err = validate_date_str(target_date)
        if not ok:
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
        return schedules, target_date

    @staticmethod
    def check_anonymous_booking(anonymous_code, schedule_id, target_date):
        ok, err = validate_anonymous_code(anonymous_code)
        if not ok:
            raise ValidationError(err)
        if not schedule_id:
            raise ValidationError('缺少排班ID')
        ok, err = validate_date_str(target_date)
        if not ok:
            raise ValidationError('日期格式不正确')

        conn = get_conn()
        c = conn.cursor()
        c.execute("""SELECT s.*, r.room_number, cou.name as counselor_name 
                     FROM schedules s JOIN rooms r ON s.room_id = r.id
                     JOIN counselors cou ON s.counselor_id = cou.id
                     WHERE s.id = ?""", (schedule_id,))
        sched = dict_row(c.fetchone())
        conn.close()
        if not sched:
            raise ValidationError('排班不存在')

        target_dt = datetime.strptime(target_date, '%Y-%m-%d').date()
        cd_flag, cd_until = is_in_cooldown(anonymous_code, target_dt)
        if cd_flag:
            raise BusinessError(f'您正处于冷静期，至{cd_until}后方可预约')

        au = get_anonymous_user(anonymous_code)
        if au and au.get('risk_level') == 'high':
            raise BusinessError(
                f'您的账号当前处于高风险状态（{au.get("risk_reason", "行为异常")}），请联系工作人员处理'
            )

        capacity_info = check_schedule_capacity(schedule_id)
        if capacity_info is None:
            raise ValidationError('排班不存在')
        if capacity_info['full']:
            raise ConflictError(f'该时段已满员（{capacity_info["booked"]}/{capacity_info["capacity"]}）')

        conflict = check_concurrent_appointment(anonymous_code, target_date, sched['start_time'], sched['end_time'])
        if conflict:
            raise ConflictError(
                f'同时段已有预约：{conflict["counselor_name"]} {conflict["start_time"]}-{conflict["end_time"]} ({conflict["room_number"]})'
            )

        counselor_conflict = check_appointment_counselor_conflict(
            sched['counselor_id'], target_date, sched['start_time'], sched['end_time']
        )
        if counselor_conflict:
            raise ConflictError(
                f'咨询师时段冲突：{sched["counselor_name"]} 在 {sched["start_time"]}-{sched["end_time"]} 于 {counselor_conflict["room_number"]} 已有预约'
            )

        room_conflict = check_appointment_room_conflict(
            sched['room_id'], target_date, sched['start_time'], sched['end_time']
        )
        if room_conflict:
            raise ConflictError(
                f'房间冲突：{sched["room_number"]} 在 {sched["start_time"]}-{sched["end_time"]} 已被 {room_conflict["counselor_name"]} 预约'
            )

        is_abnormal, abnormal_reasons = check_abnormal_booking(anonymous_code, target_date)
        warning_info = None
        if is_abnormal:
            warning_info = {
                'level': 'warning',
                'message': '检测到您的预约行为存在异常，请谨慎预约，频繁失约将触发冷静期。'
            }

        return {
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
            'abnormal_reasons': abnormal_reasons,
        }

    @staticmethod
    def submit_anonymous_booking(anonymous_code, schedule_id, target_date):
        ok, err = validate_anonymous_code(anonymous_code)
        if not ok:
            raise ValidationError(err)

        target_dt = datetime.strptime(target_date, '%Y-%m-%d').date()
        cd_flag, cd_until = is_in_cooldown(anonymous_code, target_dt)
        if cd_flag:
            raise BusinessError(f'冷静期内（至{cd_until}）不能预约')

        au_check = get_anonymous_user(anonymous_code)
        if au_check and au_check.get('risk_level') == 'high':
            raise BusinessError('您的账号处于高风险状态，暂无法预约，请联系工作人员')

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
                raise ValidationError('排班不存在')

            conflict = check_concurrent_appointment(anonymous_code, target_date, sched['start_time'], sched['end_time'])
            if conflict:
                conn.rollback()
                raise ConflictError('同时段已有有效预约')

            capacity_info = check_schedule_capacity_with_lock(schedule_id, conn)
            if capacity_info is None:
                conn.rollback()
                raise ValidationError('排班不存在')
            if capacity_info['full']:
                conn.rollback()
                raise ConflictError(
                    f'该时段已满员（{capacity_info["booked"]}/{capacity_info["capacity"]}），请选择其他时段'
                )

            counselor_conflict = check_appointment_counselor_conflict(
                sched['counselor_id'], target_date, sched['start_time'], sched['end_time']
            )
            if counselor_conflict:
                conn.rollback()
                raise ConflictError(
                    f'咨询师时段冲突：{sched["counselor_id"]}号咨询师 于 {sched["start_time"]}-{sched["end_time"]} 在房间 {counselor_conflict["room_number"]} 已有预约'
                )

            room_conflict = check_appointment_room_conflict(
                sched['room_id'], target_date, sched['start_time'], sched['end_time']
            )
            if room_conflict:
                conn.rollback()
                raise ConflictError(
                    f'房间冲突：{sched["room_id"]}号房间 在 {sched["start_time"]}-{sched["end_time"]} 已被 {room_conflict["counselor_name"]} 预约'
                )

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
                          (risk_level, risk_reason, now_str(), au['id']))
                if risk_level in ('medium', 'high'):
                    c.execute("""INSERT INTO risk_warnings 
                        (anonymous_user_id, anonymous_code, warning_type, risk_level, description, appointment_id)
                        VALUES (?, ?, ?, ?, ?, ?)""",
                        (au['id'], anonymous_code, 'abnormal_booking', risk_level,
                         f'异常预约行为：{abnormal_reason}', apt_id))
                    NotificationService.send_risk_warning(
                        f'风险预警：异常预约行为',
                        f'用户 {anonymous_code} 存在异常预约行为：{abnormal_reason}',
                        apt_id
                    )

            conn.commit()

            c.execute("""SELECT a.*, r.room_number, cou.name as counselor_name 
                         FROM appointments a JOIN rooms r ON a.room_id = r.id
                         JOIN counselors cou ON a.counselor_id = cou.id
                         WHERE a.appointment_no = ?""", (apt_no,))
            apt = dict_row(c.fetchone())
            conn.close()

            return {
                'appointment': apt,
                'is_abnormal': is_abnormal,
                'abnormal_reasons': abnormal_reasons,
            }

        except Exception as e:
            conn.rollback()
            conn.close()
            raise BusinessError(f'预约失败：{str(e)}')

    @staticmethod
    def get_appointments_for_date(filter_date, status='all', risk_filter='all', q=''):
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
        conn.close()
        return appts
