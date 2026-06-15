import falcon
from datetime import datetime, date
from app.templates import render_template
from app.services.appointment_service import AppointmentService
from app.services.permission_service import PermissionService
from app.utils.validators import calculate_checkin_info
from app.utils.response import set_html_response, set_json_response
from app.utils.exceptions import AppException, handle_exception
from config import CHECKIN_WINDOW_MINUTES_BEFORE, CHECKIN_WINDOW_MINUTES_AFTER, NO_SHOW_THRESHOLD, COOLDOWN_DAYS


class AnonymousBookPage:
    def on_get(self, req, resp):
        target_date = req.get_param('date') or date.today().isoformat()
        schedules, target_date = AppointmentService.get_schedules_for_date(target_date)
        set_html_response(resp, render_template('anonymous_book.html', {
            'target_date': target_date,
            'schedules': schedules,
            'threshold': NO_SHOW_THRESHOLD,
            'cooldown_days': COOLDOWN_DAYS,
            'year': datetime.now().year,
        }))


class AnonymousBookCheck:
    def on_post(self, req, resp):
        try:
            form = req.get_media() or {}
            anonymous_code = (form.get('anonymous_code') or '').strip()
            schedule_id = form.get('schedule_id')
            target_date = (form.get('target_date') or '').strip()
            result = AppointmentService.check_anonymous_booking(anonymous_code, schedule_id, target_date)
            resp.media = {'ok': True, **result}
        except AppException as e:
            handle_exception(req, resp, e, None)


class AnonymousBookSubmit:
    def on_post(self, req, resp):
        try:
            form = req.get_media() or {}
            anonymous_code = (form.get('anonymous_code') or '').strip()
            schedule_id = form.get('schedule_id')
            target_date = (form.get('target_date') or '').strip()
            result = AppointmentService.submit_anonymous_booking(anonymous_code, schedule_id, target_date)
            set_html_response(resp, render_template('_book_success.html', result))
        except AppException as e:
            handle_exception(req, resp, e, None)


class AppointmentsPage:
    def on_get(self, req, resp):
        user = PermissionService.require_permission(req, 'view_appointments')
        today = date.today().isoformat()
        filter_date = req.get_param('date') or today
        status = req.get_param('status') or 'all'
        risk_filter = req.get_param('risk') or 'all'
        q = req.get_param('q') or ''

        appts = AppointmentService.get_appointments_for_date(filter_date, status, risk_filter, q)

        for apt in appts:
            checkin_info = calculate_checkin_info(
                apt['appointment_date'], apt['start_time'], apt['end_time'],
                apt['checkin_status'], apt['no_show_marked'], apt.get('checkin_time')
            )
            apt.update(checkin_info)

        set_html_response(resp, render_template('appointments.html', {
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
        }))
