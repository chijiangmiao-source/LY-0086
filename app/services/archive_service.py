import json
from datetime import datetime, date, timedelta
from app.database import (
    get_conn, dict_rows, dict_row,
    create_intervention_archive, get_intervention_archives, get_intervention_archive,
)
from app.utils.validators import validate_required, validate_int
from app.utils.exceptions import ValidationError, BusinessError, NotFoundError
from app.utils.helpers import clean_str, safe_json_loads
from app.utils.validators import mask_anonymous_code


TYPE_LABELS = {
    'crisis_intervention': '危机干预',
    'followup_intervention': '回访干预',
    'noshow_intervention': '失约干预',
    'risk_intervention': '风险干预',
    'consultation': '咨询辅导',
    'referral': '转介',
    'other': '其他',
}

LEVEL_LABELS = {
    'mild': '轻度',
    'moderate': '中度',
    'severe': '重度',
    'critical': '危急',
}


class ArchiveService:

    @staticmethod
    def get_archives(filters=None, limit=100):
        archives = get_intervention_archives(filters, limit)
        return archives

    @staticmethod
    def get_archive_detail(archive_id):
        archive = get_intervention_archive(int(archive_id))
        if not archive:
            raise NotFoundError('归档记录不存在')
        return archive

    @staticmethod
    def get_basic_stats():
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as total, SUM(CASE WHEN is_closed = 1 THEN 1 ELSE 0 END) as closed FROM intervention_archives")
        stats = dict_row(c.fetchone())
        conn.close()
        return stats

    @staticmethod
    def get_counselors():
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT id, name FROM counselors WHERE is_active = 1 ORDER BY name")
        counselors = dict_rows(c.fetchall())
        conn.close()
        return counselors

    @staticmethod
    def create_archive(anonymous_user_id=None, anonymous_code='', intervention_type='other',
                       intervention_level=None, intervention_methods=None,
                       intervention_content='', intervention_effect='',
                       follow_up_plan='', appointment_id=None,
                       risk_warning_id=None, supervision_task_id=None,
                       counselor_id=None):
        ok, err = validate_required(intervention_type, '干预类型')
        if not ok:
            raise ValidationError(err)

        archive_id, archive_no = create_intervention_archive(
            anonymous_user_id=anonymous_user_id,
            anonymous_code=anonymous_code,
            intervention_type=intervention_type,
            intervention_level=intervention_level,
            intervention_methods=intervention_methods,
            intervention_content=clean_str(intervention_content),
            intervention_effect=clean_str(intervention_effect),
            follow_up_plan=clean_str(follow_up_plan),
            appointment_id=appointment_id,
            risk_warning_id=risk_warning_id,
            supervision_task_id=supervision_task_id,
            counselor_id=counselor_id,
        )
        return archive_id, archive_no

    @staticmethod
    def close_archive(archive_id, closed_by, closing_remark=''):
        if not archive_id:
            raise ValidationError('缺少归档记录ID')
        StateService = __import__('app.services.state_service', fromlist=['StateService']).StateService
        StateService.close_archive(archive_id, closed_by, clean_str(closing_remark))

    @staticmethod
    def enrich_archives(archives):
        for a in archives:
            if a.get('intervention_methods'):
                a['parsed_methods'] = safe_json_loads(a['intervention_methods'], [])
            else:
                a['parsed_methods'] = []
            if a.get('anonymous_code'):
                a['masked_code'] = mask_anonymous_code(a['anonymous_code'])
        return archives

    @staticmethod
    def export_to_csv(archives, date_from='', date_to=''):
        lines = []
        lines.append('干预结果归档报表')
        lines.append(f'统计周期：{date_from or "全部"} ~ {date_to or "全部"}')
        lines.append('')
        lines.append('归档编号,匿名编码,干预类型,干预级别,咨询师,创建时间,状态')
        for a in archives:
            status = '已结案' if a.get('is_closed') else '进行中'
            type_label = TYPE_LABELS.get(a.get('intervention_type', ''), a.get('intervention_type', ''))
            level_label = LEVEL_LABELS.get(a.get('intervention_level', ''), a.get('intervention_level', ''))
            lines.append(
                f'{a.get("archive_no","")},{a.get("masked_code","")},{type_label},{level_label},'
                f'{a.get("counselor_name","") or ""},{a.get("created_at","")},{status}'
            )
        return '\n'.join(lines)
