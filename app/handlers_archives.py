import falcon
from datetime import datetime, date
from app.templates import render_template
from app.services.archive_service import ArchiveService
from app.services.permission_service import PermissionService
from app.utils.response import set_html_response, set_csv_response
from app.utils.exceptions import AppException, handle_exception


class InterventionArchivesPage:
    def on_get(self, req, resp):
        user = PermissionService.require_permission(req, 'view_intervention_archives')
        can_manage = PermissionService.can(req, 'manage_intervention_archives')

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

        archives = ArchiveService.get_archives(filters, limit=100)
        archives = ArchiveService.enrich_archives(archives)
        counselors = ArchiveService.get_counselors()
        stats = ArchiveService.get_basic_stats()

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

        set_html_response(resp, render_template('intervention_archives.html', {
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
        }))


class InterventionArchiveApi:
    def on_get(self, req, resp):
        try:
            PermissionService.require_permission(req, 'view_intervention_archives')
            archive_id = req.get_param('id')
            if archive_id:
                archive = ArchiveService.get_archive_detail(archive_id)
                resp.media = {'archive': archive}
            else:
                archives = ArchiveService.get_archives(limit=50)
                archives = ArchiveService.enrich_archives(archives)
                resp.media = {'archives': archives}
        except AppException as e:
            handle_exception(req, resp, e, None)

    def on_post(self, req, resp):
        try:
            PermissionService.require_permission(req, 'manage_intervention_archives')
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

            archive_id, archive_no = ArchiveService.create_archive(
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
        except AppException as e:
            handle_exception(req, resp, e, None)


class InterventionArchiveCloseApi:
    def on_post(self, req, resp):
        try:
            user = PermissionService.require_permission(req, 'manage_intervention_archives')
            form = req.get_media() or {}
            archive_id = form.get('archive_id')
            closing_remark = (form.get('closing_remark') or '').strip()
            ArchiveService.close_archive(archive_id, user['user_id'], closing_remark)
            resp.media = {'success': True}
        except AppException as e:
            handle_exception(req, resp, e, None)


class InterventionArchiveExportApi:
    def on_get(self, req, resp):
        try:
            PermissionService.require_permission(req, 'view_intervention_archives')

            date_from = req.get_param('date_from') or ''
            date_to = req.get_param('date_to') or ''

            filters = {}
            if date_from:
                filters['date_from'] = date_from
            if date_to:
                filters['date_to'] = date_to

            archives = ArchiveService.get_archives(filters, limit=1000)
            archives = ArchiveService.enrich_archives(archives)
            csv_content = ArchiveService.export_to_csv(archives, date_from, date_to)
            title = f'干预归档报表_{date_from or "all"}_{date_to or "all"}'
            set_csv_response(resp, csv_content, title)
        except AppException as e:
            handle_exception(req, resp, e, None)
