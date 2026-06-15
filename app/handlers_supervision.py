import falcon
from datetime import datetime, date
from app.templates import render_template
from app.services.supervision_service import SupervisionService
from app.services.permission_service import PermissionService
from app.services.statistics_service import StatisticsService
from app.utils.response import set_html_response, set_json_response
from app.utils.exceptions import AppException, handle_exception


class SupervisionPage:
    def on_get(self, req, resp):
        user = PermissionService.require_permission(req, 'view_supervision')
        can_manage = PermissionService.can(req, 'manage_supervision')
        can_assign = PermissionService.can(req, 'assign_supervision')

        status_filter = req.get_param('status') or 'all'
        priority_filter = req.get_param('priority') or 'all'
        task_type_filter = req.get_param('type') or 'all'
        anonymous_code = req.get_param('code') or ''
        is_overdue = req.get_param('overdue') or ''
        my_tasks = req.get_param('mine') or ''

        filters = {}
        if status_filter != 'all':
            filters['status'] = status_filter
        if priority_filter != 'all':
            filters['priority'] = priority_filter
        if task_type_filter != 'all':
            filters['task_type'] = task_type_filter
        if anonymous_code:
            filters['anonymous_code'] = anonymous_code
        if is_overdue == '1':
            filters['is_overdue'] = '1'
        if my_tasks == '1':
            filters['assigned_to'] = user['user_id']

        result = SupervisionService.get_tasks(filters, limit=100)
        tasks = SupervisionService.enrich_task_overdue_info(result['tasks'])
        summary = SupervisionService.get_summary()
        my_summary = SupervisionService.get_summary(user_id=user['user_id'])
        users = SupervisionService.get_users_for_assign()

        set_html_response(resp, render_template('supervision.html', {
            'user': user,
            'tasks': tasks,
            'summary': summary,
            'my_summary': my_summary,
            'users': users,
            'can_manage': can_manage,
            'can_assign': can_assign,
            'status_filter': status_filter,
            'priority_filter': priority_filter,
            'task_type_filter': task_type_filter,
            'anonymous_code': anonymous_code,
            'is_overdue': is_overdue,
            'my_tasks': my_tasks,
            'status_labels': result['status_labels'],
            'priority_labels': result['priority_labels'],
            'type_labels': result['type_labels'],
            'nav': 'supervision',
            'year': datetime.now().year,
        }))


class SupervisionApi:
    def on_get(self, req, resp):
        try:
            PermissionService.require_permission(req, 'view_supervision')
            task_id = req.get_param('id')
            if task_id:
                task = SupervisionService.get_task_detail(task_id)
                resp.media = {'task': task}
            else:
                status = req.get_param('status') or ''
                priority = req.get_param('priority') or ''
                filters = {}
                if status:
                    filters['status'] = status
                if priority:
                    filters['priority'] = priority
                result = SupervisionService.get_tasks(filters, limit=50)
                tasks = SupervisionService.enrich_task_overdue_info(result['tasks'])
                resp.media = {'tasks': tasks}
        except AppException as e:
            handle_exception(req, resp, e, None)

    def on_post(self, req, resp):
        try:
            user = PermissionService.require_permission(req, 'manage_supervision')
            form = req.get_media() or {}
            task_type = form.get('task_type', 'other')
            priority = form.get('priority', 'normal')
            title = (form.get('title') or '').strip()
            description = (form.get('description') or '').strip()
            anonymous_user_id = form.get('anonymous_user_id')
            anonymous_code = form.get('anonymous_code', '')
            appointment_id = form.get('appointment_id')
            followup_survey_id = form.get('followup_survey_id')
            risk_warning_id = form.get('risk_warning_id')
            assigned_to = form.get('assigned_to')
            deadline_hours = form.get('deadline_hours')

            task_id, task_no = SupervisionService.create_task(
                task_type=task_type,
                priority=priority,
                title=title,
                description=description,
                anonymous_user_id=anonymous_user_id,
                anonymous_code=anonymous_code,
                appointment_id=appointment_id,
                followup_survey_id=followup_survey_id,
                risk_warning_id=risk_warning_id,
                assigned_to=assigned_to,
                assigned_by=user['user_id'],
                deadline_hours=deadline_hours,
            )
            resp.media = {'success': True, 'task_id': task_id, 'task_no': task_no}
        except AppException as e:
            handle_exception(req, resp, e, None)


class SupervisionStatusApi:
    def on_post(self, req, resp):
        try:
            user = PermissionService.require_permission(req, 'manage_supervision')
            form = req.get_media() or {}
            task_id = form.get('task_id')
            status = form.get('status')
            remark = (form.get('remark') or '').strip()
            SupervisionService.update_status(task_id, status, user['user_id'], remark)
            resp.media = {'success': True}
        except AppException as e:
            handle_exception(req, resp, e, None)


class SupervisionAssignApi:
    def on_post(self, req, resp):
        try:
            user = PermissionService.require_permission(req, 'assign_supervision')
            form = req.get_media() or {}
            task_id = form.get('task_id')
            assigned_to = form.get('assigned_to')
            remark = (form.get('remark') or '').strip()
            SupervisionService.assign_task(task_id, assigned_to, user['user_id'], remark)
            resp.media = {'success': True}
        except AppException as e:
            handle_exception(req, resp, e, None)


class SupervisionSummaryApi:
    def on_get(self, req, resp):
        try:
            PermissionService.require_permission(req, 'view_supervision')
            user = req.context.user
            mine = req.get_param('mine') or ''
            if mine == '1':
                summary = SupervisionService.get_summary(user_id=user['user_id'])
            else:
                summary = SupervisionService.get_summary()
            resp.media = {'summary': summary}
        except AppException as e:
            handle_exception(req, resp, e, None)
