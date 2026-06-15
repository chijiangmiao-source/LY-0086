import falcon
import json
from datetime import datetime, date, timedelta
from app.templates import render_template
from app.database import (
    get_conn, dict_rows, dict_row, has_permission,
    create_intervention_archive, get_intervention_archives, get_intervention_archive,
    close_intervention_archive,
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

class InterventionArchivesPage:
    def on_get(self, req, resp):
        user = req.context.user
        if not has_permission(user['role'], 'view_intervention_archives'):
            resp.status = falcon.HTTP_403
            resp.text = '权限不足'
            return

        can_manage = has_permission(user['role'], 'manage_intervention_archives')

        status_filter = req.get_param('status') or 'all'
        type_filter = req.get_param('type') or 'all'
        level_filter = req.get_param('level') or 'all'
        anonymous_code = req.get_param('code') or ''
        date_from = req.get_param('date_from') or ''
        date_to = req.get_param('date_to') or ''

        filters = {}
        if status_filter == 'closed':
            filters['is_closed'] = 1
        elif status_filter == 'open':
            filters['is_closed'] = 0
        if type_filter != 'all':
            filters['intervention_type'] = type_filter
        if level_filter != 'all':
            filters['intervention_level'] = level_filter
        if anonymous_code:
            filters['anonymous_code'] = anonymous_code
        if date_from:
            filters['date_from'] = date_from
        if date_to:
            filters['date_to'] = date_to

        archives = get_intervention_archives(filters, limit=100)

        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT id, name FROM counselors WHERE is_active = 1 ORDER BY name")
        counselors = dict_rows(c.fetchall())
        c.execute("SELECT COUNT(*) as total, SUM(CASE WHEN is_closed = 1 THEN 1 ELSE 0 END) as closed FROM intervention_archives")
        stats = dict_row(c.fetchone())
        conn.close()

        type_labels = {
            'crisis_intervention': '危机干预',
            'followup_intervention': '回访干预',
            'noshow_intervention': '失约干预',
            'risk_intervention': '风险干预',
            'consultation': '咨询辅导',
            'referral': '转介',
            'other': '其他',
        }
        level_labels = {
            'mild': '轻度',
            'moderate': '中度',
            'severe': '重度',
            'critical': '危急',
        }

        resp.content_type = 'text/html; charset=utf-8'
        resp.text = render_template('intervention_archives.html', {
            'user': user,
            'archives': archives,
            'counselors': counselors,
            'stats': stats,
            'can_manage': can_manage,
            'status_filter': status_filter,
            'type_filter': type_filter,
            'level_filter': level_filter,
            'anonymous_code': anonymous_code,
            'date_from': date_from,
            'date_to': date_to,
            'type_labels': type_labels,
            'level_labels': level_labels,
            'nav': 'archives',
            'year': datetime.now().year,
        })

class InterventionArchiveApi:
    def on_get(self, req, resp):
        if not require_permission(req, resp, 'view_intervention_archives'):
            return
        archive_id = req.get_param('id')
        if archive_id:
            archive = get_intervention_archive(int(archive_id))
            if not archive:
                resp.status = falcon.HTTP_404
                resp.media = {'error': '归档记录不存在'}
                return
            resp.media = {'archive': archive}
        else:
            archives = get_intervention_archives(limit=50)
            resp.media = {'archives': archives}

    def on_post(self, req, resp):
        if not require_permission(req, resp, 'manage_intervention_archives'):
            return
        user = req.context.user
        form = req.get_media() or {}

        anonymous_user_id = form.get('anonymous_user_id')
        anonymous_code = form.get('anonymous_code', '')
        intervention_type = form.get('intervention_type', 'other')
        intervention_level = form.get('intervention_level')
        intervention_methods = form.get('intervention_methods')
        intervention_content = (form.get('intervention_content') or '').strip()
        intervention_effect = (form.get('intervention_effect') or '').strip()
        follow_up_plan = (form.get('follow_up_plan') or '').strip()
        appointment_id = form.get('appointment_id')
        risk_warning_id = form.get('risk_warning_id')
        supervision_task_id = form.get('supervision_task_id')
        counselor_id = form.get('counselor_id')

        if not intervention_type:
            resp.status = falcon.HTTP_400
            resp.media = {'error': '干预类型不能为空'}
            return

        archive_id, archive_no = create_intervention_archive(
            anonymous_user_id=anonymous_user_id,
            anonymous_code=anonymous_code,
            intervention_type=intervention_type,
            intervention_level=intervention_level,
            intervention_methods=intervention_methods,
            intervention_content=intervention_content,
            intervention_effect=intervention_effect,
            follow_up_plan=follow_up_plan,
            appointment_id=appointment_id,
            risk_warning_id=risk_warning_id,
            supervision_task_id=supervision_task_id,
            counselor_id=counselor_id,
        )

        resp.media = {'success': True, 'archive_id': archive_id, 'archive_no': archive_no}

class InterventionArchiveCloseApi:
    def on_post(self, req, resp):
        if not require_permission(req, resp, 'manage_intervention_archives'):
            return
        user = req.context.user
        form = req.get_media() or {}
        archive_id = form.get('archive_id')
        closing_remark = (form.get('closing_remark') or '').strip()

        if not archive_id:
            resp.status = falcon.HTTP_400
            resp.media = {'error': '缺少归档记录ID'}
            return

        success = close_intervention_archive(int(archive_id), user['user_id'], closing_remark)
        if not success:
            resp.status = falcon.HTTP_404
            resp.media = {'error': '归档记录不存在'}
            return

        resp.media = {'success': True}

class InterventionArchiveExportApi:
    def on_get(self, req, resp):
        if not require_permission(req, resp, 'view_intervention_archives'):
            resp.status = falcon.HTTP_403
            resp.media = {'error': '权限不足'}
            return

        date_from = req.get_param('date_from') or ''
        date_to = req.get_param('date_to') or ''

        filters = {}
        if date_from:
            filters['date_from'] = date_from
        if date_to:
            filters['date_to'] = date_to

        archives = get_intervention_archives(filters, limit=1000)

        type_labels = {
            'crisis_intervention': '危机干预',
            'followup_intervention': '回访干预',
            'noshow_intervention': '失约干预',
            'risk_intervention': '风险干预',
            'consultation': '咨询辅导',
            'referral': '转介',
            'other': '其他',
        }
        level_labels = {
            'mild': '轻度',
            'moderate': '中度',
            'severe': '重度',
            'critical': '危急',
        }

        lines = []
        lines.append('干预结果归档报表')
        lines.append(f'统计周期：{date_from or "全部"} ~ {date_to or "全部"}')
        lines.append('')
        lines.append('归档编号,匿名编码,干预类型,干预级别,咨询师,创建时间,状态')
        for a in archives:
            status = '已结案' if a.get('is_closed') else '进行中'
            type_label = type_labels.get(a.get('intervention_type', ''), a.get('intervention_type', ''))
            level_label = level_labels.get(a.get('intervention_level', ''), a.get('intervention_level', ''))
            lines.append(f'{a.get("archive_no","")},{a.get("masked_code","")},{type_label},{level_label},{a.get("counselor_name","") or ""},{a.get("created_at","")},{status}')

        csv_content = '\n'.join(lines)
        resp.content_type = 'text/csv; charset=utf-8'
        title = f'干预归档报表_{date_from or "all"}_{date_to or "all"}'
        resp.append_header('Content-Disposition', f'attachment; filename="{title}.csv"')
        resp.text = '\ufeff' + csv_content
