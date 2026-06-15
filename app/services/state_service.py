from datetime import datetime, timedelta, date
from app.database import (
    get_conn, dict_row,
    update_supervision_task_status, assign_supervision_task,
    close_intervention_archive, close_high_risk_tracking,
    add_high_risk_tracking_log,
)
from app.utils.helpers import now_str
from app.utils.exceptions import BusinessError, NotFoundError


SUPERVISION_VALID_STATUSES = ['pending', 'in_progress', 'completed', 'cancelled']
SUPERVISION_STATUS_TRANSITIONS = {
    'pending': ['in_progress', 'completed', 'cancelled'],
    'in_progress': ['completed', 'cancelled', 'pending'],
    'completed': [],
    'cancelled': [],
}

HIGH_RISK_VALID_STATUSES = ['monitoring', 'intervening', 'recovering', 'closed']
HIGH_RISK_STATUS_TRANSITIONS = {
    'monitoring': ['intervening', 'recovering', 'closed'],
    'intervening': ['monitoring', 'recovering', 'closed'],
    'recovering': ['monitoring', 'intervening', 'closed'],
    'closed': [],
}

APPOINTMENT_CHECKIN_STATUSES = ['pending', 'checked_in', 'cancelled']


class StateService:

    @staticmethod
    def validate_transition(current_status, target_status, valid_transitions, entity_name='实体'):
        if target_status not in valid_transitions:
            raise BusinessError(f'无效的{entity_name}状态值：{target_status}')
        allowed = valid_transitions.get(current_status, [])
        if target_status not in allowed and current_status != target_status:
            raise BusinessError(f'{entity_name}状态不允许从 {current_status} 变更为 {target_status}')
        return True

    @staticmethod
    def transition_supervision_status(task_id, new_status, operator_id=None, remark=''):
        if new_status not in SUPERVISION_VALID_STATUSES:
            raise BusinessError(f'无效的督办任务状态值：{new_status}')
        success = update_supervision_task_status(int(task_id), new_status, operator_id, remark)
        if not success:
            raise NotFoundError('督办任务不存在')
        return True

    @staticmethod
    def assign_supervision(task_id, assigned_to, assigned_by=None, remark=''):
        success = assign_supervision_task(int(task_id), int(assigned_to), assigned_by, remark)
        if not success:
            raise NotFoundError('督办任务不存在')
        return True

    @staticmethod
    def close_archive(archive_id, closed_by, closing_remark=''):
        success = close_intervention_archive(int(archive_id), closed_by, closing_remark)
        if not success:
            raise NotFoundError('归档记录不存在')
        return True

    @staticmethod
    def close_high_risk_tracking(tracking_id, closed_by, closing_reason):
        success = close_high_risk_tracking(int(tracking_id), closed_by, closing_reason)
        if not success:
            raise NotFoundError('跟踪记录不存在')
        return True

    @staticmethod
    def add_high_risk_log(tracking_id, operator_id, log_type, content='',
                          mood_score=None, risk_assessment=None):
        success = add_high_risk_tracking_log(
            tracking_id=int(tracking_id),
            operator_id=operator_id,
            log_type=log_type,
            content=content,
            mood_score=mood_score,
            risk_assessment=risk_assessment,
        )
        if not success:
            raise NotFoundError('跟踪记录不存在')
        return True

    @staticmethod
    def calculate_deadline(priority, deadline_hours=None):
        from config import SUPERVISION_URGENT_HOURS, SUPERVISION_HIGH_HOURS, SUPERVISION_NORMAL_HOURS
        if deadline_hours is None:
            if priority == 'urgent':
                deadline_hours = SUPERVISION_URGENT_HOURS
            elif priority == 'high':
                deadline_hours = SUPERVISION_HIGH_HOURS
            else:
                deadline_hours = SUPERVISION_NORMAL_HOURS
        return (datetime.now() + timedelta(hours=deadline_hours)).strftime('%Y-%m-%d %H:%M:%S')

    @staticmethod
    def calculate_task_overdue(deadline_str, status):
        if not deadline_str or status in ('completed', 'cancelled'):
            return {
                'remaining_hours': None,
                'is_overdue': False,
                'overdue_hours': 0,
            }
        try:
            deadline_dt = datetime.strptime(deadline_str, '%Y-%m-%d %H:%M:%S')
            now = datetime.now()
            remaining = deadline_dt - now
            remaining_hours = round(remaining.total_seconds() / 3600, 1)
            is_overdue = remaining.total_seconds() < 0
            overdue_hours = round(abs(remaining.total_seconds()) / 3600, 1) if is_overdue else 0
            return {
                'remaining_hours': remaining_hours,
                'is_overdue': is_overdue,
                'overdue_hours': overdue_hours,
            }
        except (ValueError, TypeError):
            return {
                'remaining_hours': None,
                'is_overdue': False,
                'overdue_hours': 0,
            }

    @staticmethod
    def calculate_next_followup_date(interval_days=None):
        from config import HIGH_RISK_FOLLOWUP_INTERVAL_DAYS
        if interval_days is None:
            interval_days = HIGH_RISK_FOLLOWUP_INTERVAL_DAYS
        return (date.today() + timedelta(days=interval_days)).isoformat()

    @staticmethod
    def calculate_followup_due(next_followup_date_str):
        if not next_followup_date_str:
            return {
                'days_until_followup': None,
                'is_followup_due': False,
            }
        try:
            next_dt = datetime.strptime(next_followup_date_str, '%Y-%m-%d').date()
            today = date.today()
            days_until = (next_dt - today).days
            return {
                'days_until_followup': days_until,
                'is_followup_due': days_until <= 0,
            }
        except (ValueError, TypeError):
            return {
                'days_until_followup': None,
                'is_followup_due': False,
            }
