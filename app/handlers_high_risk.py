import falcon
import json
from datetime import datetime, date, timedelta
from app.templates import render_template
from app.database import (
    get_conn, dict_rows, dict_row, has_permission,
    create_high_risk_tracking, get_high_risk_trackings, get_high_risk_tracking,
    add_high_risk_tracking_log, close_high_risk_tracking,
    get_high_risk_tracking_summary,
)

def require_permission(req, resp, permission):
    user = req.context.user
    if not user:
        resp.status = falcon.HTTP_401
        resp.content_type = 'application/json'
        resp.text = '{"error": "未登录"}'
        return False
    if not has_permission(user['role'], permission):
        resp.status = falcon.HTTP_403
        resp.content_type = 'application/json'
        resp.text = '{"error": "权限不足"}'
        return False
    return True

class HighRiskTrackingPage:
    def on_get(self, req, resp):
        user = req.context.user
        if not has_permission(user['role'], 'view_high_risk_tracking'):
            resp.status = falcon.HTTP_403
            resp.text = '权限不足'
            return

        can_manage = has_permission(user['role'], 'manage_high_risk_tracking')

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

        trackings = get_high_risk_trackings(filters, limit=100)
        summary = get_high_risk_tracking_summary()

        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT id, name FROM counselors WHERE is_active = 1 ORDER BY name")
        counselors = dict_rows(c.fetchall())
        c.execute("SELECT id, real_name, role FROM users WHERE role IN ('admin', 'intervention') ORDER BY real_name")
        supervisors = dict_rows(c.fetchall())
        conn.close()

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

        resp.content_type = 'text/html; charset=utf-8'
        resp.text = render_template('high_risk_tracking.html', {
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
        })

class HighRiskTrackingDetailPage:
    def on_get(self, req, resp, tracking_id):
        user = req.context.user
        if not has_permission(user['role'], 'view_high_risk_tracking'):
            resp.status = falcon.HTTP_403
            resp.text = '权限不足'
            return

        can_manage = has_permission(user['role'], 'manage_high_risk_tracking')
        tracking = get_high_risk_tracking(int(tracking_id))

        if not tracking:
            resp.status = falcon.HTTP_404
            resp.text = '跟踪记录不存在'
            return

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

        if tracking.get('anonymous_code') and len(tracking['anonymous_code']) > 6:
            tracking['masked_code'] = tracking['anonymous_code'][:4] + '***' + tracking['anonymous_code'][-2:]
        else:
            tracking['masked_code'] = tracking['anonymous_code'][:3] + '***' if tracking.get('anonymous_code') else '***'

        for log in tracking.get('logs', []):
            log['type_label'] = log_type_labels.get(log.get('log_type', ''), log.get('log_type', ''))

        resp.content_type = 'text/html; charset=utf-8'
        resp.text = render_template('high_risk_detail.html', {
            'user': user,
            'tracking': tracking,
            'can_manage': can_manage,
            'status_labels': status_labels,
            'risk_labels': risk_labels,
            'log_type_labels': log_type_labels,
            'nav': 'high_risk',
            'year': datetime.now().year,
        })

class HighRiskTrackingApi:
    def on_get(self, req, resp):
        if not require_permission(req, resp, 'view_high_risk_tracking'):
            return
        tracking_id = req.get_param('id')
        if tracking_id:
            tracking = get_high_risk_tracking(int(tracking_id))
            if not tracking:
                resp.status = falcon.HTTP_404
                resp.media = {'error': '跟踪记录不存在'}
                return
            resp.media = {'tracking': tracking}
        else:
            trackings = get_high_risk_trackings(limit=50)
            resp.media = {'trackings': trackings}

    def on_post(self, req, resp):
        if not require_permission(req, resp, 'manage_high_risk_tracking'):
            return
        user = req.context.user
        form = req.get_media() or {}

        anonymous_user_id = form.get('anonymous_user_id')
        anonymous_code = form.get('anonymous_code', '')
        initial_risk_reason = (form.get('initial_risk_reason') or '').strip()
        assigned_counselor_id = form.get('assigned_counselor_id')
        assigned_supervisor_id = form.get('assigned_supervisor_id') or user['user_id']

        if not anonymous_user_id or not anonymous_code:
            resp.status = falcon.HTTP_400
            resp.media = {'error': '缺少匿名用户信息'}
            return

        tracking_id, tracking_no = create_high_risk_tracking(
            anonymous_user_id=anonymous_user_id,
            anonymous_code=anonymous_code,
            initial_risk_reason=initial_risk_reason,
            assigned_counselor_id=assigned_counselor_id,
            assigned_supervisor_id=assigned_supervisor_id,
        )

        resp.media = {'success': True, 'tracking_id': tracking_id, 'tracking_no': tracking_no}

class HighRiskTrackingLogApi:
    def on_post(self, req, resp):
        if not require_permission(req, resp, 'manage_high_risk_tracking'):
            return
        user = req.context.user
        form = req.get_media() or {}

        tracking_id = form.get('tracking_id')
        log_type = form.get('log_type', 'note')
        content = (form.get('content') or '').strip()
        mood_score = form.get('mood_score')
        risk_assessment = form.get('risk_assessment')

        if not tracking_id:
            resp.status = falcon.HTTP_400
            resp.media = {'error': '缺少跟踪记录ID'}
            return

        if mood_score:
            try:
                mood_score = int(mood_score)
            except (ValueError, TypeError):
                mood_score = None

        success = add_high_risk_tracking_log(
            tracking_id=int(tracking_id),
            operator_id=user['user_id'],
            log_type=log_type,
            content=content,
            mood_score=mood_score,
            risk_assessment=risk_assessment,
        )

        if not success:
            resp.status = falcon.HTTP_404
            resp.media = {'error': '跟踪记录不存在'}
            return

        resp.media = {'success': True}

class HighRiskTrackingCloseApi:
    def on_post(self, req, resp):
        if not require_permission(req, resp, 'manage_high_risk_tracking'):
            return
        user = req.context.user
        form = req.get_media() or {}
        tracking_id = form.get('tracking_id')
        closing_reason = (form.get('closing_reason') or '').strip()

        if not tracking_id:
            resp.status = falcon.HTTP_400
            resp.media = {'error': '缺少跟踪记录ID'}
            return

        if not closing_reason:
            resp.status = falcon.HTTP_400
            resp.media = {'error': '请填写结案原因'}
            return

        success = close_high_risk_tracking(int(tracking_id), user['user_id'], closing_reason)
        if not success:
            resp.status = falcon.HTTP_404
            resp.media = {'error': '跟踪记录不存在'}
            return

        resp.media = {'success': True}

class HighRiskTrackingSummaryApi:
    def on_get(self, req, resp):
        if not require_permission(req, resp, 'view_high_risk_tracking'):
            return
        summary = get_high_risk_tracking_summary()
        resp.media = {'summary': summary}
