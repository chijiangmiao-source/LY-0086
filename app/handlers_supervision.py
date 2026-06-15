import falcon
import json
from datetime import datetime, date, timedelta
from app.templates import render_template
from app.database import (
    get_conn, dict_rows, dict_row, has_permission,
    create_supervision_task, get_supervision_tasks, get_supervision_task,
    update_supervision_task_status, assign_supervision_task,
    get_supervision_summary,
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

class SupervisionPage:
    def on_get(self, req, resp):
        user = req.context.user
        if not has_permission(user['role'], 'view_supervision'):
            resp.status = falcon.HTTP_403
            resp.text = '权限不足'
            return

        can_manage = has_permission(user['role'], 'manage_supervision')
        can_assign = has_permission(user['role'], 'assign_supervision')

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

        tasks = get_supervision_tasks(filters, limit=100)
        summary = get_supervision_summary()
        my_summary = get_supervision_summary(user_id=user['user_id'])

        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT id, real_name, username, role FROM users ORDER BY real_name")
        users = dict_rows(c.fetchall())
        conn.close()

        status_labels = {
            'pending': '待处理',
            'in_progress': '处理中',
            'completed': '已完成',
            'cancelled': '已取消',
        }
        priority_labels = {
            'urgent': '紧急',
            'high': '高',
            'normal': '普通',
            'low': '低',
        }
        type_labels = {
            'followup_critical': '回访紧急',
            'followup_important': '回访重要',
            'followup_general': '回访一般',
            'risk_warning': '风险预警',
            'checkin_anomaly': '签到异常',
            'noshow_intervention': '失约干预',
            'other': '其他',
        }

        resp.content_type = 'text/html; charset=utf-8'
        resp.text = render_template('supervision.html', {
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
            'status_labels': status_labels,
            'priority_labels': priority_labels,
            'type_labels': type_labels,
            'nav': 'supervision',
            'year': datetime.now().year,
        })

class SupervisionApi:
    def on_get(self, req, resp):
        if not require_permission(req, resp, 'view_supervision'):
            return
        task_id = req.get_param('id')
        if task_id:
            task = get_supervision_task(int(task_id))
            if not task:
                resp.status = falcon.HTTP_404
                resp.media = {'error': '任务不存在'}
                return
            resp.media = {'task': task}
        else:
            status = req.get_param('status') or ''
            priority = req.get_param('priority') or ''
            filters = {}
            if status:
                filters['status'] = status
            if priority:
                filters['priority'] = priority
            tasks = get_supervision_tasks(filters, limit=50)
            resp.media = {'tasks': tasks}

    def on_post(self, req, resp):
        if not require_permission(req, resp, 'manage_supervision'):
            return
        user = req.context.user
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

        if not title:
            resp.status = falcon.HTTP_400
            resp.media = {'error': '任务标题不能为空'}
            return

        if deadline_hours:
            try:
                deadline_hours = int(deadline_hours)
            except (ValueError, TypeError):
                deadline_hours = None

        task_id, task_no = create_supervision_task(
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

class SupervisionStatusApi:
    def on_post(self, req, resp):
        if not require_permission(req, resp, 'manage_supervision'):
            return
        user = req.context.user
        form = req.get_media() or {}
        task_id = form.get('task_id')
        status = form.get('status')
        remark = (form.get('remark') or '').strip()

        if not task_id or not status:
            resp.status = falcon.HTTP_400
            resp.media = {'error': '缺少必要参数'}
            return

        valid_statuses = ['pending', 'in_progress', 'completed', 'cancelled']
        if status not in valid_statuses:
            resp.status = falcon.HTTP_400
            resp.media = {'error': '无效的状态值'}
            return

        success = update_supervision_task_status(int(task_id), status, user['user_id'], remark)
        if not success:
            resp.status = falcon.HTTP_404
            resp.media = {'error': '任务不存在'}
            return

        resp.media = {'success': True}

class SupervisionAssignApi:
    def on_post(self, req, resp):
        if not require_permission(req, resp, 'assign_supervision'):
            return
        user = req.context.user
        form = req.get_media() or {}
        task_id = form.get('task_id')
        assigned_to = form.get('assigned_to')
        remark = (form.get('remark') or '').strip()

        if not task_id or not assigned_to:
            resp.status = falcon.HTTP_400
            resp.media = {'error': '缺少必要参数'}
            return

        success = assign_supervision_task(int(task_id), int(assigned_to), user['user_id'], remark)
        if not success:
            resp.status = falcon.HTTP_404
            resp.media = {'error': '任务不存在'}
            return

        resp.media = {'success': True}

class SupervisionSummaryApi:
    def on_get(self, req, resp):
        if not require_permission(req, resp, 'view_supervision'):
            return
        user = req.context.user
        mine = req.get_param('mine') or ''
        if mine == '1':
            summary = get_supervision_summary(user_id=user['user_id'])
        else:
            summary = get_supervision_summary()
        resp.media = {'summary': summary}
