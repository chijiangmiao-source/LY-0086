from datetime import datetime, date, timedelta
from app.database import (
    get_conn, dict_rows, dict_row,
    create_high_risk_tracking, get_high_risk_trackings, get_high_risk_tracking,
    get_high_risk_tracking_summary,
)
from app.utils.validators import validate_required, validate_int
from app.utils.exceptions import ValidationError, BusinessError, NotFoundError
from app.utils.helpers import clean_str
from app.utils.validators import mask_anonymous_code
from app.services.state_service import StateService


STATUS_LABELS = {
    'monitoring': '跟踪观察',
    'intervening': '干预中',
    'recovering': '恢复期',
    'closed': '已结案',
}

RISK_LABELS = {
    'high': '高风险',
    'medium': '中风险',
    'low': '低风险',
}

LOG_TYPE_LABELS = {
    'init': '建立台账',
    'followup': '随访记录',
    'intervention': '干预记录',
    'assessment': '风险评估',
    'note': '备注',
    'close': '结案',
}


class HighRiskService:

    @staticmethod
    def get_trackings(filters=None, limit=100):
        trackings = get_high_risk_trackings(filters, limit)
        return trackings

    @staticmethod
    def get_tracking_detail(tracking_id):
        tracking = get_high_risk_tracking(int(tracking_id))
        if not tracking:
            raise NotFoundError('跟踪记录不存在')
        return tracking

    @staticmethod
    def get_summary():
        return get_high_risk_tracking_summary()

    @staticmethod
    def get_counselors():
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT id, name FROM counselors WHERE is_active = 1 ORDER BY name")
        counselors = dict_rows(c.fetchall())
        conn.close()
        return counselors

    @staticmethod
    def get_supervisors():
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT id, real_name, role FROM users WHERE role IN ('admin', 'intervention') ORDER BY real_name")
        supervisors = dict_rows(c.fetchall())
        conn.close()
        return supervisors

    @staticmethod
    def create_tracking(anonymous_user_id, anonymous_code, initial_risk_reason='',
                        assigned_counselor_id=None, assigned_supervisor_id=None):
        if not anonymous_user_id or not anonymous_code:
            raise ValidationError('缺少匿名用户信息')

        tracking_id, tracking_no = create_high_risk_tracking(
            anonymous_user_id=anonymous_user_id,
            anonymous_code=anonymous_code,
            initial_risk_reason=clean_str(initial_risk_reason),
            assigned_counselor_id=assigned_counselor_id,
            assigned_supervisor_id=assigned_supervisor_id,
        )
        return tracking_id, tracking_no

    @staticmethod
    def add_log(tracking_id, operator_id, log_type, content='',
                mood_score=None, risk_assessment=None):
        if not tracking_id:
            raise ValidationError('缺少跟踪记录ID')

        if mood_score:
            ok, ms = validate_int(mood_score, 0, 10)
            if ok:
                mood_score = ms
            else:
                mood_score = None

        StateService.add_high_risk_log(
            tracking_id=tracking_id,
            operator_id=operator_id,
            log_type=log_type,
            content=clean_str(content),
            mood_score=mood_score,
            risk_assessment=risk_assessment,
        )

    @staticmethod
    def close_tracking(tracking_id, closed_by, closing_reason):
        if not tracking_id:
            raise ValidationError('缺少跟踪记录ID')
        ok, err = validate_required(closing_reason, '结案原因')
        if not ok:
            raise ValidationError(err)
        StateService.close_high_risk_tracking(tracking_id, closed_by, clean_str(closing_reason))

    @staticmethod
    def enrich_trackings(trackings):
        for t in trackings:
            if t.get('anonymous_code'):
                t['masked_code'] = mask_anonymous_code(t['anonymous_code'])
            if t.get('next_followup_date'):
                followup_info = StateService.calculate_followup_due(t['next_followup_date'])
                t.update(followup_info)
        return trackings

    @staticmethod
    def enrich_tracking_detail(tracking):
        if tracking.get('anonymous_code'):
            tracking['masked_code'] = mask_anonymous_code(tracking['anonymous_code'])
        for log in tracking.get('logs', []):
            log['type_label'] = LOG_TYPE_LABELS.get(log.get('log_type', ''), log.get('log_type', ''))
        return tracking
