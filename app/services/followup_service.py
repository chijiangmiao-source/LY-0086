import json
from datetime import datetime, date, timedelta
from app.database import (
    get_conn, dict_rows, dict_row,
    get_active_followup_questions, get_all_followup_questions,
    add_followup_question, update_followup_question,
    get_eligible_appointments_for_followup, submit_followup_survey,
    get_followup_surveys, get_followup_survey_by_appointment,
    mark_followup_abnormal, grade_followup_abnormal,
    check_create_followup_supervision,
    get_high_risk_followup_warnings, create_high_risk_tracking,
)
from app.utils.validators import validate_anonymous_code, parse_satisfaction_score, validate_required
from app.utils.exceptions import ValidationError, BusinessError, NotFoundError
from app.utils.helpers import safe_json_loads, safe_json_dumps, clean_str
from app.utils.validators import mask_anonymous_code


class FollowupService:

    @staticmethod
    def get_surveys(filters=None, limit=100):
        surveys = get_followup_surveys(filters, limit)
        rebook_labels = {'yes': '愿意', 'no': '不愿意', 'undecided': '待定'}
        for s in surveys:
            s['rebook_label'] = rebook_labels.get(s['rebook_willingness'], s['rebook_willingness'])
            s['masked_code'] = mask_anonymous_code(s.get('anonymous_code'))
        return surveys

    @staticmethod
    def get_survey_detail(survey_id):
        conn = get_conn()
        c = conn.cursor()
        c.execute("""SELECT fs.*, cou.name as counselor_name,
                            a.appointment_no, a.appointment_date, a.start_time, a.end_time
                     FROM followup_surveys fs
                     LEFT JOIN counselors cou ON fs.counselor_id = cou.id
                     LEFT JOIN appointments a ON fs.appointment_id = a.id
                     WHERE fs.id = ?""", (survey_id,))
        survey = dict_row(c.fetchone())
        conn.close()
        if not survey:
            raise NotFoundError('回访记录不存在')
        survey['parsed_responses'] = safe_json_loads(survey.get('responses'))
        survey['masked_code'] = mask_anonymous_code(survey.get('anonymous_code'))
        return survey

    @staticmethod
    def get_active_questions_with_parsed_options():
        questions = get_active_followup_questions()
        for q in questions:
            q['parsed_options'] = safe_json_loads(q.get('options'), []) if q.get('question_type') == 'choice' else []
        return questions

    @staticmethod
    def get_all_questions():
        return get_all_followup_questions()

    @staticmethod
    def add_question(question_text, question_type, options=None, sort_order=0):
        ok, err = validate_required(question_text, '问题内容')
        if not ok:
            raise ValidationError(err)
        opts_json = safe_json_dumps(options) if isinstance(options, list) else options
        return add_followup_question(question_text, question_type, opts_json, sort_order)

    @staticmethod
    def update_question(question_id, **kwargs):
        params = {}
        if 'question_text' in kwargs:
            params['question_text'] = clean_str(kwargs['question_text'])
        if 'question_type' in kwargs:
            params['question_type'] = kwargs['question_type']
        if 'options' in kwargs:
            opts = kwargs['options']
            params['options'] = safe_json_dumps(opts) if isinstance(opts, list) else opts
        if 'sort_order' in kwargs:
            params['sort_order'] = int(kwargs['sort_order'])
        if 'is_active' in kwargs:
            params['is_active'] = int(kwargs['is_active'])
        update_followup_question(question_id, **params)

    @staticmethod
    def get_eligible_appointments(anonymous_code):
        if not anonymous_code:
            return []
        return get_eligible_appointments_for_followup(anonymous_code)

    @staticmethod
    def submit_survey(appointment_id, anonymous_code, satisfaction_score=None,
                      rebook_willingness='undecided', responses=None, comment=''):
        if not appointment_id or not anonymous_code:
            raise ValidationError('缺少必要参数')

        ok, score = parse_satisfaction_score(satisfaction_score)
        if not ok:
            raise ValidationError(score)

        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM appointments WHERE id = ? AND anonymous_code = ?", (appointment_id, anonymous_code))
        apt = dict_row(c.fetchone())
        conn.close()

        if not apt:
            raise NotFoundError('预约不存在或编码不匹配')

        if apt['checkin_status'] != 'checked_in':
            raise BusinessError('只有已签到的咨询才能填写回访')

        end_time_str = f"{apt['appointment_date']} {apt['end_time']}"
        try:
            end_dt = datetime.strptime(end_time_str, '%Y-%m-%d %H:%M')
            if datetime.now() < end_dt:
                raise BusinessError('咨询尚未结束，请在咨询结束后再填写回访')
        except (ValueError, TypeError):
            pass

        existing = get_followup_survey_by_appointment(appointment_id)
        if existing:
            raise BusinessError('该预约已提交过回访')

        survey_id = submit_followup_survey(
            appointment_id=appointment_id,
            anonymous_code=anonymous_code,
            anonymous_user_id=apt.get('anonymous_user_id'),
            counselor_id=apt.get('counselor_id'),
            satisfaction_score=score,
            rebook_willingness=rebook_willingness,
            responses=responses or {},
            comment=clean_str(comment),
        )

        if survey_id is None:
            raise BusinessError('提交失败，该预约已存在回访记录')

        grade_result = grade_followup_abnormal(survey_id)
        supervision_result = check_create_followup_supervision(survey_id)

        if grade_result and grade_result['grade'] == 'critical':
            if apt.get('anonymous_user_id'):
                create_high_risk_tracking(
                    anonymous_user_id=apt['anonymous_user_id'],
                    anonymous_code=anonymous_code,
                    initial_risk_reason=grade_result['reasons'][0] if grade_result['reasons'] else '回访高风险',
                )

        return {
            'survey_id': survey_id,
            'grade': grade_result['grade'] if grade_result else 'normal',
            'has_supervision': supervision_result is not None,
        }

    @staticmethod
    def mark_abnormal(survey_id, is_abnormal, abnormal_reason='', is_high_risk=None, high_risk_reason=None):
        if not survey_id:
            raise ValidationError('缺少回访记录ID')
        if is_high_risk is None:
            is_high_risk = 1 if is_abnormal == 1 and '高风险' in abnormal_reason else None
        if is_high_risk == 1 and not high_risk_reason:
            high_risk_reason = abnormal_reason or '人工标记高风险'
        mark_followup_abnormal(survey_id, is_abnormal, abnormal_reason, is_high_risk, high_risk_reason)

    @staticmethod
    def get_high_risk_warnings(limit=50):
        warnings = get_high_risk_followup_warnings(limit)
        for w in warnings:
            w['masked_code'] = mask_anonymous_code(w.get('anonymous_code'))
        return warnings

    @staticmethod
    def get_counselors_for_filter():
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT id, name FROM counselors WHERE is_active = 1 ORDER BY name")
        counselors = dict_rows(c.fetchall())
        conn.close()
        return counselors
