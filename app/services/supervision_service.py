import json
from datetime import datetime, date, timedelta
from app.database import (
    get_conn, dict_rows, dict_row,
    create_supervision_task, get_supervision_tasks, get_supervision_task,
    get_supervision_summary,
)
from app.utils.validators import validate_required, validate_int
from app.utils.exceptions import ValidationError, BusinessError, NotFoundError
from app.utils.helpers import clean_str
from app.utils.validators import mask_anonymous_code
from app.services.state_service import StateService


STATUS_LABELS = {
    'pending': '待处理',
    'in_progress': '处理中',
    'completed': '已完成',
    'cancelled': '已取消',
}

PRIORITY_LABELS = {
    'urgent': '紧急',
    'high': '高',
    'normal': '普通',
    'low': '低',
}

TYPE_LABELS = {
    'followup_critical': '回访紧急',
    'followup_important': '回访重要',
    'followup_general': '回访一般',
    'risk_warning': '风险预警',
    'checkin_anomaly': '签到异常',
    'noshow_intervention': '失约干预',
    'other': '其他',
}

VALID_STATUSES = ['pending', 'in_progress', 'completed', 'cancelled']


class SupervisionService:

    @staticmethod
    def get_tasks(filters=None, limit=100):
        tasks = get_supervision_tasks(filters, limit)
        return {
            'tasks': tasks,
            'status_labels': STATUS_LABELS,
            'priority_labels': PRIORITY_LABELS,
            'type_labels': TYPE_LABELS,
        }

    @staticmethod
    def get_task_detail(task_id):
        task = get_supervision_task(int(task_id))
        if not task:
            raise NotFoundError('任务不存在')
        return task

    @staticmethod
    def get_summary(user_id=None):
        return get_supervision_summary(user_id=user_id)

    @staticmethod
    def get_users_for_assign():
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT id, real_name, username, role FROM users ORDER BY real_name")
        users = dict_rows(c.fetchall())
        conn.close()
        return users

    @staticmethod
    def create_task(task_type, priority, title, description='',
                    anonymous_user_id=None, anonymous_code=None,
                    appointment_id=None, followup_survey_id=None,
                    risk_warning_id=None, assigned_to=None, assigned_by=None,
                    deadline_hours=None):
        ok, err = validate_required(title, '任务标题')
        if not ok:
            raise ValidationError(err)

        if deadline_hours:
            ok, dh = validate_int(deadline_hours, 1)
            if not ok:
                deadline_hours = None
            else:
                deadline_hours = dh

        task_id, task_no = create_supervision_task(
            task_type=task_type,
            priority=priority,
            title=clean_str(title),
            description=clean_str(description),
            anonymous_user_id=anonymous_user_id,
            anonymous_code=anonymous_code,
            appointment_id=appointment_id,
            followup_survey_id=followup_survey_id,
            risk_warning_id=risk_warning_id,
            assigned_to=assigned_to,
            assigned_by=assigned_by,
            deadline_hours=deadline_hours,
        )
        return task_id, task_no

    @staticmethod
    def update_status(task_id, status, operator_id=None, remark=''):
        if not task_id or not status:
            raise ValidationError('缺少必要参数')
        if status not in VALID_STATUSES:
            raise ValidationError('无效的状态值')
        StateService.transition_supervision_status(task_id, status, operator_id, clean_str(remark))

    @staticmethod
    def assign_task(task_id, assigned_to, assigned_by=None, remark=''):
        if not task_id or not assigned_to:
            raise ValidationError('缺少必要参数')
        StateService.assign_supervision(task_id, assigned_to, assigned_by, clean_str(remark))

    @staticmethod
    def enrich_task_overdue_info(tasks):
        for t in tasks:
            overdue_info = StateService.calculate_task_overdue(t.get('deadline'), t.get('status'))
            t.update(overdue_info)
            if t.get('anonymous_code'):
                t['masked_code'] = mask_anonymous_code(t['anonymous_code'])
        return tasks
