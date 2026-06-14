import falcon
from datetime import datetime, date, timedelta
from app.templates import render_template
from app.database import (get_conn, dict_rows, dict_row, has_permission,
                          get_unresolved_risk_warnings, resolve_risk_warning,
                          get_role_permissions)

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

class RiskWarningsPage:
    def on_get(self, req, resp):
        user = req.context.user
        if not has_permission(user['role'], 'view_risk_warnings'):
            resp.status = falcon.HTTP_403
            resp.text = '权限不足'
            return
        can_manage = has_permission(user['role'], 'manage_risk_warnings')

        status_filter = req.get_param('status') or 'unresolved'
        risk_level = req.get_param('level') or 'all'

        conn = get_conn()
        c = conn.cursor()

        query = """SELECT rw.*, au.no_show_count, au.cooldown_until, au.risk_level as user_risk_level
                     FROM risk_warnings rw
                     LEFT JOIN anonymous_users au ON rw.anonymous_user_id = au.id
                     WHERE 1=1"""
        params = []

        if status_filter == 'unresolved':
            query += " AND rw.is_resolved = 0"
        elif status_filter == 'resolved':
            query += " AND rw.is_resolved = 1"

        if risk_level != 'all':
            query += " AND rw.risk_level = ?"
            params.append(risk_level)

        query += """ ORDER BY 
                        CASE rw.risk_level 
                            WHEN 'high' THEN 1 
                            WHEN 'medium' THEN 2 
                            ELSE 3 
                        END,
                        rw.created_at DESC
                     LIMIT 100"""

        c.execute(query, params)
        warnings = dict_rows(c.fetchall())

        c.execute("""SELECT risk_level, COUNT(*) as cnt 
                     FROM risk_warnings 
                     WHERE is_resolved = 0 
                     GROUP BY risk_level""")
        level_counts = {row['risk_level']: row['cnt'] for row in c.fetchall()}

        c.execute("SELECT COUNT(*) as cnt FROM risk_warnings WHERE is_resolved = 0")
        total_unresolved = c.fetchone()['cnt']

        c.execute("""SELECT au.*, 
                            (SELECT COUNT(*) FROM appointments a 
                             WHERE a.anonymous_user_id = au.id AND a.no_show_marked = 1) as total_noshow,
                            (SELECT COUNT(*) FROM appointments a
                             WHERE a.anonymous_user_id = au.id) as total_appts
                     FROM anonymous_users au 
                     WHERE au.risk_level = 'high'
                     ORDER BY au.no_show_count DESC
                     LIMIT 20""")
        high_risk_users = dict_rows(c.fetchall())

        conn.close()

        warning_types = {
            'consecutive_noshow': '连续失约',
            'abnormal_booking': '异常预约',
            'checkin_anomaly': '签到异常',
            'high_cancel_rate': '高取消率',
            'followup_high_risk': '回访高风险',
            'other': '其他',
        }

        for w in warnings:
            w['type_label'] = warning_types.get(w['warning_type'], w['warning_type'])

        resp.content_type = 'text/html; charset=utf-8'
        resp.text = render_template('risk_warnings.html', {
            'user': user,
            'warnings': warnings,
            'high_risk_users': high_risk_users,
            'can_manage': can_manage,
            'status_filter': status_filter,
            'risk_level': risk_level,
            'level_counts': level_counts,
            'total_unresolved': total_unresolved,
            'warning_types': warning_types,
            'nav': 'risk',
            'year': datetime.now().year,
        })

class ResolveWarningApi:
    def on_post(self, req, resp):
        if not require_permission(req, resp, 'manage_risk_warnings'):
            return
        user = req.context.user
        form = req.get_media() or {}
        warning_id = form.get('warning_id')
        note = form.get('resolution_note', '')
        if not warning_id:
            resp.status = falcon.HTTP_400
            resp.content_type = 'application/json'
            resp.text = '{"error": "预警ID必填"}'
            return
        resolve_risk_warning(warning_id, user['user_id'], note)
        resp.media = {'success': True}

class RiskUsersPage:
    def on_get(self, req, resp):
        user = req.context.user
        if not has_permission(user['role'], 'view_risk_warnings'):
            resp.status = falcon.HTTP_403
            resp.text = '权限不足'
            return

        level_filter = req.get_param('level') or 'all'
        q = req.get_param('q') or ''

        conn = get_conn()
        c = conn.cursor()

        query = """SELECT au.*,
                          (SELECT COUNT(*) FROM appointments a 
                           WHERE a.anonymous_user_id = au.id) as total_appts,
                          (SELECT COUNT(*) FROM appointments a
                           WHERE a.anonymous_user_id = au.id AND a.no_show_marked = 1) as noshow_count,
                          (SELECT COUNT(*) FROM appointments a
                           WHERE a.anonymous_user_id = au.id AND a.checkin_status = 'cancelled') as cancel_count
                   FROM anonymous_users au
                   WHERE 1=1"""
        params = []

        if level_filter != 'all':
            query += " AND au.risk_level = ?"
            params.append(level_filter)

        if q:
            query += " AND au.anonymous_code LIKE ?"
            params.append(f'%{q}%')

        query += """ ORDER BY 
                        CASE au.risk_level 
                            WHEN 'high' THEN 1 
                            WHEN 'medium' THEN 2 
                            ELSE 3 
                        END,
                        au.no_show_count DESC"""

        c.execute(query, params)
        users = dict_rows(c.fetchall())

        for u in users:
            total = u['total_appts'] or 0
            u['noshow_rate'] = round(u['noshow_count'] / total * 100, 1) if total > 0 else 0
            u['cancel_rate'] = round(u['cancel_count'] / total * 100, 1) if total > 0 else 0

        c.execute("SELECT risk_level, COUNT(*) as cnt FROM anonymous_users GROUP BY risk_level")
        level_counts = {row['risk_level']: row['cnt'] for row in c.fetchall()}
        high_count = level_counts.get('high', 0)
        medium_count = level_counts.get('medium', 0)
        low_count = level_counts.get('low', 0)
        total_count = high_count + medium_count + low_count

        conn.close()

        resp.content_type = 'text/html; charset=utf-8'
        resp.text = render_template('risk_users.html', {
            'user': user,
            'risk_users': users,
            'level_filter': level_filter,
            'q': q,
            'high_count': high_count,
            'medium_count': medium_count,
            'low_count': low_count,
            'total_count': total_count,
            'nav': 'risk',
            'year': datetime.now().year,
        })
