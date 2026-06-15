from datetime import datetime, date, timedelta
from app.database import (
    get_conn, dict_rows, dict_row,
    get_unresolved_risk_warnings, resolve_risk_warning,
)
from app.utils.validators import validate_required
from app.utils.exceptions import ValidationError, NotFoundError
from app.utils.helpers import clean_str


WARNING_TYPE_LABELS = {
    'consecutive_noshow': '连续失约',
    'abnormal_booking': '异常预约',
    'checkin_anomaly': '签到异常',
    'high_cancel_rate': '高取消率',
    'followup_high_risk': '回访高风险',
    'other': '其他',
}


class RiskService:

    @staticmethod
    def get_warnings(status_filter='unresolved', risk_level='all', limit=100):
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
                     LIMIT ?"""
        params.append(limit)

        c.execute(query, params)
        warnings = dict_rows(c.fetchall())

        for w in warnings:
            w['type_label'] = WARNING_TYPE_LABELS.get(w['warning_type'], w['warning_type'])

        c.execute("""SELECT risk_level, COUNT(*) as cnt 
                     FROM risk_warnings 
                     WHERE is_resolved = 0 
                     GROUP BY risk_level""")
        level_counts = {row['risk_level']: row['cnt'] for row in c.fetchall()}

        c.execute("SELECT COUNT(*) as cnt FROM risk_warnings WHERE is_resolved = 0")
        total_unresolved = c.fetchone()['cnt']

        conn.close()

        return {
            'warnings': warnings,
            'level_counts': level_counts,
            'total_unresolved': total_unresolved,
            'warning_types': WARNING_TYPE_LABELS,
        }

    @staticmethod
    def get_high_risk_users(limit=20):
        conn = get_conn()
        c = conn.cursor()
        c.execute("""SELECT au.*, 
                            (SELECT COUNT(*) FROM appointments a 
                             WHERE a.anonymous_user_id = au.id AND a.no_show_marked = 1) as total_noshow,
                            (SELECT COUNT(*) FROM appointments a
                             WHERE a.anonymous_user_id = au.id) as total_appts
                     FROM anonymous_users au 
                     WHERE au.risk_level = 'high'
                     ORDER BY au.no_show_count DESC
                     LIMIT ?""", (limit,))
        users = dict_rows(c.fetchall())
        conn.close()
        return users

    @staticmethod
    def resolve_warning(warning_id, operator_id, resolution_note=''):
        if not warning_id:
            raise ValidationError('预警ID必填')
        resolve_risk_warning(warning_id, operator_id, clean_str(resolution_note))

    @staticmethod
    def get_risk_users(level_filter='all', q=''):
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

        return {
            'users': users,
            'high_count': high_count,
            'medium_count': medium_count,
            'low_count': low_count,
            'total_count': total_count,
        }
