import falcon
from datetime import datetime, date
from app.templates import render_template
from app.services.risk_service import RiskService
from app.services.permission_service import PermissionService
from app.utils.response import set_html_response
from app.utils.exceptions import AppException, handle_exception


class RiskWarningsPage:
    def on_get(self, req, resp):
        user = PermissionService.require_permission(req, 'view_risk_warnings')
        can_manage = PermissionService.can(req, 'manage_risk_warnings')

        status_filter = req.get_param('status') or 'unresolved'
        risk_level = req.get_param('level') or 'all'

        warning_data = RiskService.get_warnings(status_filter, risk_level)
        high_risk_users = RiskService.get_high_risk_users(20)

        set_html_response(resp, render_template('risk_warnings.html', {
            'user': user,
            'warnings': warning_data['warnings'],
            'high_risk_users': high_risk_users,
            'can_manage': can_manage,
            'status_filter': status_filter,
            'risk_level': risk_level,
            'level_counts': warning_data['level_counts'],
            'total_unresolved': warning_data['total_unresolved'],
            'warning_types': warning_data['warning_types'],
            'nav': 'risk',
            'year': datetime.now().year,
        }))


class ResolveWarningApi:
    def on_post(self, req, resp):
        try:
            user = PermissionService.require_permission(req, 'manage_risk_warnings')
            form = req.get_media() or {}
            warning_id = form.get('warning_id')
            note = form.get('resolution_note', '')
            RiskService.resolve_warning(warning_id, user['user_id'], note)
            resp.media = {'success': True}
        except AppException as e:
            handle_exception(req, resp, e, None)


class RiskUsersPage:
    def on_get(self, req, resp):
        user = PermissionService.require_permission(req, 'view_risk_warnings')

        level_filter = req.get_param('level') or 'all'
        q = req.get_param('q') or ''

        risk_data = RiskService.get_risk_users(level_filter, q)

        set_html_response(resp, render_template('risk_users.html', {
            'user': user,
            'risk_users': risk_data['users'],
            'level_filter': level_filter,
            'q': q,
            'high_count': risk_data['high_count'],
            'medium_count': risk_data['medium_count'],
            'low_count': risk_data['low_count'],
            'total_count': risk_data['total_count'],
            'nav': 'risk',
            'year': datetime.now().year,
        }))
