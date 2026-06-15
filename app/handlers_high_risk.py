import falcon
from datetime import datetime, date
from app.templates import render_template
from app.services.high_risk_service import HighRiskService
from app.services.permission_service import PermissionService
from app.utils.response import set_html_response
from app.utils.exceptions import AppException, handle_exception


class HighRiskTrackingPage:
    def on_get(self, req, resp):
        user = PermissionService.require_permission(req, 'view_high_risk_tracking')
        can_manage = PermissionService.can(req, 'manage_high_risk_tracking')

        status_filter = req.get_param('status') or 'all'
        risk_filter = req.get_param('risk') or 'all'
        anonymous_code = req.get_param('code') or ''

        filters = {}
        if status_filter == 'active':
            filters['is_closed'] = 0
        elif status_filter == 'closed':
            filters['is_closed'] = 1
        if risk_filter != 'all':
            filters['risk_level'] = risk_filter
        if anonymous_code:
            filters['anonymous_code'] = anonymous_code

        trackings = HighRiskService.get_trackings(filters, limit=100)
        trackings = HighRiskService.enrich_trackings(trackings)
        summary = HighRiskService.get_summary()
        counselors = HighRiskService.get_counselors()
        supervisors = HighRiskService.get_supervisors()

        status_labels = {
            'monitoring': '跟踪观察',
            'intervening': '干预中',
            'recovering': '恢复期',
            'closed': '已结案',
        }
        risk_labels = {
            'high': '高风险',
            'medium': '中风险',
            'low': '低风险',
        }

        set_html_response(resp, render_template('high_risk_tracking.html', {
            'user': user,
            'trackings': trackings,
            'summary': summary,
            'counselors': counselors,
            'supervisors': supervisors,
            'can_manage': can_manage,
            'status_filter': status_filter,
            'risk_filter': risk_filter,
            'anonymous_code': anonymous_code,
            'status_labels': status_labels,
            'risk_labels': risk_labels,
            'nav': 'high_risk',
            'year': datetime.now().year,
        }))


class HighRiskTrackingDetailPage:
    def on_get(self, req, resp, tracking_id):
        user = PermissionService.require_permission(req, 'view_high_risk_tracking')
        can_manage = PermissionService.can(req, 'manage_high_risk_tracking')
        tracking = HighRiskService.get_tracking_detail(tracking_id)
        tracking = HighRiskService.enrich_tracking_detail(tracking)

        status_labels = {
            'monitoring': '跟踪观察',
            'intervening': '干预中',
            'recovering': '恢复期',
            'closed': '已结案',
        }
        risk_labels = {
            'high': '高风险',
            'medium': '中风险',
            'low': '低风险',
        }
        log_type_labels = {
            'init': '建立台账',
            'followup': '随访记录',
            'intervention': '干预记录',
            'assessment': '风险评估',
            'note': '备注',
            'close': '结案',
        }

        set_html_response(resp, render_template('high_risk_detail.html', {
            'user': user,
            'tracking': tracking,
            'can_manage': can_manage,
            'status_labels': status_labels,
            'risk_labels': risk_labels,
            'log_type_labels': log_type_labels,
            'nav': 'high_risk',
            'year': datetime.now().year,
        }))


class HighRiskTrackingApi:
    def on_get(self, req, resp):
        try:
            PermissionService.require_permission(req, 'view_high_risk_tracking')
            tracking_id = req.get_param('id')
            if tracking_id:
                tracking = HighRiskService.get_tracking_detail(tracking_id)
                tracking = HighRiskService.enrich_tracking_detail(tracking)
                resp.media = {'tracking': tracking}
            else:
                trackings = HighRiskService.get_trackings(limit=50)
                trackings = HighRiskService.enrich_trackings(trackings)
                resp.media = {'trackings': trackings}
        except AppException as e:
            handle_exception(req, resp, e, None)

    def on_post(self, req, resp):
        try:
            user = PermissionService.require_permission(req, 'manage_high_risk_tracking')
            form = req.get_media() or {}

            anonymous_user_id = form.get('anonymous_user_id')
            anonymous_code = form.get('anonymous_code', '')
            initial_risk_reason = (form.get('initial_risk_reason') or '').strip()
            assigned_counselor_id = form.get('assigned_counselor_id')
            assigned_supervisor_id = form.get('assigned_supervisor_id') or user['user_id']

            tracking_id, tracking_no = HighRiskService.create_tracking(
                anonymous_user_id=anonymous_user_id,
                anonymous_code=anonymous_code,
                initial_risk_reason=initial_risk_reason,
                assigned_counselor_id=assigned_counselor_id,
                assigned_supervisor_id=assigned_supervisor_id,
            )
            resp.media = {'success': True, 'tracking_id': tracking_id, 'tracking_no': tracking_no}
        except AppException as e:
            handle_exception(req, resp, e, None)


class HighRiskTrackingLogApi:
    def on_post(self, req, resp):
        try:
            user = PermissionService.require_permission(req, 'manage_high_risk_tracking')
            form = req.get_media() or {}

            tracking_id = form.get('tracking_id')
            log_type = form.get('log_type', 'note')
            content = (form.get('content') or '').strip()
            mood_score = form.get('mood_score')
            risk_assessment = form.get('risk_assessment')

            HighRiskService.add_log(
                tracking_id=tracking_id,
                operator_id=user['user_id'],
                log_type=log_type,
                content=content,
                mood_score=mood_score,
                risk_assessment=risk_assessment,
            )
            resp.media = {'success': True}
        except AppException as e:
            handle_exception(req, resp, e, None)


class HighRiskTrackingCloseApi:
    def on_post(self, req, resp):
        try:
            user = PermissionService.require_permission(req, 'manage_high_risk_tracking')
            form = req.get_media() or {}
            tracking_id = form.get('tracking_id')
            closing_reason = (form.get('closing_reason') or '').strip()

            HighRiskService.close_tracking(tracking_id, user['user_id'], closing_reason)
            resp.media = {'success': True}
        except AppException as e:
            handle_exception(req, resp, e, None)


class HighRiskTrackingSummaryApi:
    def on_get(self, req, resp):
        try:
            PermissionService.require_permission(req, 'view_high_risk_tracking')
            summary = HighRiskService.get_summary()
            resp.media = {'summary': summary}
        except AppException as e:
            handle_exception(req, resp, e, None)
