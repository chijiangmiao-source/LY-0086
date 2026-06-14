import falcon
import json
from datetime import datetime, date, timedelta
from app.templates import render_template
from app.database import (
    get_conn, dict_rows, dict_row, has_permission,
    get_active_followup_questions, get_all_followup_questions,
    add_followup_question, update_followup_question,
    get_eligible_appointments_for_followup, submit_followup_survey,
    get_followup_surveys, get_followup_survey_by_appointment,
    mark_followup_abnormal,
    get_satisfaction_trend, get_counselor_satisfaction_distribution,
    get_abnormal_feedback_stats, get_high_risk_followup_warnings,
    get_followup_summary_stats
)
from config import FOLLOWUP_DEFAULT_DAYS_RANGE

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

class FollowupPage:
    def on_get(self, req, resp):
        user = req.context.user
        if not has_permission(user['role'], 'view_followup'):
            resp.status = falcon.HTTP_403
            resp.text = '权限不足'
            return

        can_manage = has_permission(user['role'], 'manage_followup')

        anonymous_code = req.get_param('code') or ''
        counselor_id = req.get_param('counselor_id') or ''
        satisfaction_min = req.get_param('satisfaction_min') or ''
        satisfaction_max = req.get_param('satisfaction_max') or ''
        rebook_willingness = req.get_param('rebook') or ''
        is_abnormal = req.get_param('abnormal') or ''
        is_high_risk = req.get_param('high_risk') or ''
        date_from = req.get_param('date_from') or ''
        date_to = req.get_param('date_to') or ''

        filters = {}
        if anonymous_code:
            filters['anonymous_code'] = anonymous_code
        if counselor_id:
            filters['counselor_id'] = int(counselor_id)
        if satisfaction_min:
            filters['satisfaction_min'] = int(satisfaction_min)
        if satisfaction_max:
            filters['satisfaction_max'] = int(satisfaction_max)
        if rebook_willingness:
            filters['rebook_willingness'] = rebook_willingness
        if is_abnormal == '1':
            filters['is_abnormal'] = 1
        if is_high_risk == '1':
            filters['is_high_risk'] = 1
        if date_from:
            filters['date_from'] = date_from
        if date_to:
            filters['date_to'] = date_to

        surveys = get_followup_surveys(filters)

        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT id, name FROM counselors WHERE is_active = 1 ORDER BY name")
        counselors = dict_rows(c.fetchall())
        conn.close()

        rebook_labels = {'yes': '愿意', 'no': '不愿意', 'undecided': '待定'}

        for s in surveys:
            s['rebook_label'] = rebook_labels.get(s['rebook_willingness'], s['rebook_willingness'])
            if s['anonymous_code'] and len(s['anonymous_code']) > 6:
                s['masked_code'] = s['anonymous_code'][:4] + '***' + s['anonymous_code'][-2:]
            else:
                s['masked_code'] = s['anonymous_code'][:3] + '***' if s['anonymous_code'] else '***'

        resp.content_type = 'text/html; charset=utf-8'
        resp.text = render_template('followup.html', {
            'user': user,
            'surveys': surveys,
            'counselors': counselors,
            'can_manage': can_manage,
            'filters': {
                'anonymous_code': anonymous_code,
                'counselor_id': counselor_id,
                'satisfaction_min': satisfaction_min,
                'satisfaction_max': satisfaction_max,
                'rebook_willingness': rebook_willingness,
                'is_abnormal': is_abnormal,
                'is_high_risk': is_high_risk,
                'date_from': date_from,
                'date_to': date_to,
            },
            'nav': 'followup',
            'year': datetime.now().year,
        })

class FollowupSurveyPage:
    def on_get(self, req, resp):
        anonymous_code = req.get_param('code') or ''
        if not anonymous_code:
            resp.content_type = 'text/html; charset=utf-8'
            resp.text = render_template('followup_survey.html', {
                'error': '请提供匿名编码',
                'anonymous_code': '',
                'appointments': [],
                'questions': [],
                'selected_appointment': None,
                'year': datetime.now().year,
            })
            return

        appointments = get_eligible_appointments_for_followup(anonymous_code)
        questions = get_active_followup_questions()

        for q in questions:
            if q.get('options') and q['question_type'] == 'choice':
                try:
                    q['parsed_options'] = json.loads(q['options'])
                except (json.JSONDecodeError, TypeError):
                    q['parsed_options'] = []
            else:
                q['parsed_options'] = []

        resp.content_type = 'text/html; charset=utf-8'
        resp.text = render_template('followup_survey.html', {
            'error': None,
            'anonymous_code': anonymous_code,
            'appointments': appointments,
            'questions': questions,
            'selected_appointment': None,
            'year': datetime.now().year,
        })

class FollowupSurveySubmitApi:
    def on_post(self, req, resp):
        form = req.get_media() or {}
        appointment_id = form.get('appointment_id')
        anonymous_code = form.get('anonymous_code', '').strip()
        satisfaction_score = form.get('satisfaction_score')
        rebook_willingness = form.get('rebook_willingness', 'undecided')
        responses = form.get('responses') or {}
        comment = (form.get('comment') or '').strip()

        if not appointment_id or not anonymous_code:
            resp.status = falcon.HTTP_400
            resp.media = {'error': '缺少必要参数'}
            return

        if satisfaction_score is not None:
            try:
                satisfaction_score = int(satisfaction_score)
                if satisfaction_score < 1 or satisfaction_score > 5:
                    raise ValueError()
            except (ValueError, TypeError):
                resp.status = falcon.HTTP_400
                resp.media = {'error': '满意度评分须为1-5的整数'}
                return

        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM appointments WHERE id = ? AND anonymous_code = ?", (appointment_id, anonymous_code))
        apt = dict_row(c.fetchone())
        conn.close()

        if not apt:
            resp.status = falcon.HTTP_404
            resp.media = {'error': '预约不存在或编码不匹配'}
            return

        if apt['checkin_status'] != 'checked_in':
            resp.status = falcon.HTTP_400
            resp.media = {'error': '只有已签到的咨询才能填写回访'}
            return

        end_time_str = f"{apt['appointment_date']} {apt['end_time']}"
        try:
            end_dt = datetime.strptime(end_time_str, '%Y-%m-%d %H:%M')
            if datetime.now() < end_dt:
                resp.status = falcon.HTTP_400
                resp.media = {'error': '咨询尚未结束，请在咨询结束后再填写回访'}
                return
        except (ValueError, TypeError):
            pass

        existing = get_followup_survey_by_appointment(appointment_id)
        if existing:
            resp.status = falcon.HTTP_400
            resp.media = {'error': '该预约已提交过回访'}
            return

        survey_id = submit_followup_survey(
            appointment_id=appointment_id,
            anonymous_code=anonymous_code,
            anonymous_user_id=apt.get('anonymous_user_id'),
            counselor_id=apt.get('counselor_id'),
            satisfaction_score=satisfaction_score,
            rebook_willingness=rebook_willingness,
            responses=responses,
            comment=comment,
        )

        if survey_id is None:
            resp.status = falcon.HTTP_400
            resp.media = {'error': '提交失败，该预约已存在回访记录'}
            return

        resp.media = {'success': True, 'survey_id': survey_id}

class FollowupDetailApi:
    def on_get(self, req, resp, survey_id):
        if not require_permission(req, resp, 'view_followup'):
            return
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
            resp.status = falcon.HTTP_404
            resp.media = {'error': '回访记录不存在'}
            return
        if survey.get('responses'):
            try:
                survey['parsed_responses'] = json.loads(survey['responses'])
            except (json.JSONDecodeError, TypeError):
                survey['parsed_responses'] = {}
        else:
            survey['parsed_responses'] = {}
        if survey.get('anonymous_code') and len(survey['anonymous_code']) > 6:
            survey['masked_code'] = survey['anonymous_code'][:4] + '***' + survey['anonymous_code'][-2:]
        else:
            survey['masked_code'] = (survey['anonymous_code'][:3] + '***') if survey.get('anonymous_code') else '***'
        resp.media = survey

class FollowupMarkAbnormalApi:
    def on_post(self, req, resp):
        if not require_permission(req, resp, 'manage_followup'):
            return
        form = req.get_media() or {}
        survey_id = form.get('survey_id')
        is_abnormal = form.get('is_abnormal', 1)
        abnormal_reason = (form.get('abnormal_reason') or '').strip()
        is_high_risk = form.get('is_high_risk')
        high_risk_reason = (form.get('high_risk_reason') or '').strip()
        if not survey_id:
            resp.status = falcon.HTTP_400
            resp.media = {'error': '缺少回访记录ID'}
            return
        if is_high_risk is None:
            is_high_risk = 1 if is_abnormal == 1 and '高风险' in abnormal_reason else None
        if is_high_risk == 1 and not high_risk_reason:
            high_risk_reason = abnormal_reason or '人工标记高风险'
        mark_followup_abnormal(survey_id, is_abnormal, abnormal_reason, is_high_risk, high_risk_reason)
        resp.media = {'success': True}

class FollowupQuestionsApi:
    def on_get(self, req, resp):
        if not require_permission(req, resp, 'manage_followup'):
            return
        questions = get_all_followup_questions()
        resp.media = {'questions': questions}

    def on_post(self, req, resp):
        if not require_permission(req, resp, 'manage_followup'):
            return
        form = req.get_media() or {}
        question_text = (form.get('question_text') or '').strip()
        question_type = form.get('question_type') or 'text'
        options = form.get('options') or None
        sort_order = form.get('sort_order') or 0
        if not question_text:
            resp.status = falcon.HTTP_400
            resp.media = {'error': '问题内容不能为空'}
            return
        if isinstance(options, list):
            options = json.dumps(options, ensure_ascii=False)
        qid = add_followup_question(question_text, question_type, options, sort_order)
        resp.media = {'success': True, 'question_id': qid}

class FollowupQuestionUpdateApi:
    def on_post(self, req, resp, question_id):
        if not require_permission(req, resp, 'manage_followup'):
            return
        form = req.get_media() or {}
        kwargs = {}
        if 'question_text' in form:
            kwargs['question_text'] = form['question_text'].strip()
        if 'question_type' in form:
            kwargs['question_type'] = form['question_type']
        if 'options' in form:
            opts = form['options']
            if isinstance(opts, list):
                opts = json.dumps(opts, ensure_ascii=False)
            kwargs['options'] = opts
        if 'sort_order' in form:
            kwargs['sort_order'] = int(form['sort_order'])
        if 'is_active' in form:
            kwargs['is_active'] = int(form['is_active'])
        update_followup_question(question_id, **kwargs)
        resp.media = {'success': True}

class FollowupAnalyticsPage:
    def on_get(self, req, resp):
        user = req.context.user
        if not has_permission(user['role'], 'view_followup_analytics'):
            resp.status = falcon.HTTP_403
            resp.text = '权限不足'
            return

        days_range = int(req.get_param('days') or FOLLOWUP_DEFAULT_DAYS_RANGE)
        period = req.get_param('period') or 'week'
        end_date = date.today().isoformat()
        start_date = (date.today() - timedelta(days=days_range)).isoformat()

        summary_stats, score_dist = get_followup_summary_stats(start_date, end_date)
        satisfaction_trend = get_satisfaction_trend(start_date, end_date, period)
        counselor_stats = get_counselor_satisfaction_distribution(start_date, end_date)
        abnormal_stats = get_abnormal_feedback_stats(start_date, end_date, period)
        high_risk_warnings = get_high_risk_followup_warnings(20)

        max_trend_total = max((t['total'] for t in satisfaction_trend), default=1)
        for t in satisfaction_trend:
            t['bar_pct'] = round(t['total'] / max(max_trend_total, 1) * 100, 1)

        max_abnormal_total = max((a['total'] for a in abnormal_stats), default=1)
        for a in abnormal_stats:
            a['bar_pct'] = round(a['total'] / max(max_abnormal_total, 1) * 100, 1)

        for w in high_risk_warnings:
            if w.get('anonymous_code') and len(w['anonymous_code']) > 6:
                w['masked_code'] = w['anonymous_code'][:4] + '***' + w['anonymous_code'][-2:]
            else:
                w['masked_code'] = (w['anonymous_code'][:3] + '***') if w.get('anonymous_code') else '***'

        resp.content_type = 'text/html; charset=utf-8'
        resp.text = render_template('followup_analytics.html', {
            'user': user,
            'start_date': start_date,
            'end_date': end_date,
            'days_range': days_range,
            'period': period,
            'summary_stats': summary_stats,
            'score_dist': score_dist,
            'satisfaction_trend': satisfaction_trend,
            'counselor_stats': counselor_stats,
            'abnormal_stats': abnormal_stats,
            'high_risk_warnings': high_risk_warnings,
            'nav': 'followup_analytics',
            'year': datetime.now().year,
        })

class FollowupAnalyticsExportApi:
    def on_get(self, req, resp):
        if not require_permission(req, resp, 'view_followup_analytics'):
            resp.status = falcon.HTTP_403
            resp.content_type = 'application/json'
            resp.text = '{"error": "权限不足"}'
            return

        days_range = int(req.get_param('days') or FOLLOWUP_DEFAULT_DAYS_RANGE)
        period = req.get_param('period') or 'week'
        end_date = date.today().isoformat()
        start_date = (date.today() - timedelta(days=days_range)).isoformat()

        summary_stats, score_dist = get_followup_summary_stats(start_date, end_date)
        satisfaction_trend = get_satisfaction_trend(start_date, end_date, period)
        counselor_stats = get_counselor_satisfaction_distribution(start_date, end_date)
        abnormal_stats = get_abnormal_feedback_stats(start_date, end_date, period)

        lines = []
        lines.append('心理咨询回访与满意度追踪报表')
        lines.append(f'统计周期：{start_date} ~ {end_date}')
        lines.append('')
        lines.append('一、总体概况')
        lines.append(f'回访总量,{summary_stats.get("total", 0)}')
        lines.append(f'平均满意度,{summary_stats.get("avg_score", 0)}')
        lines.append(f'满意度（4-5分占比）,{summary_stats.get("satisfaction_rate", 0)}%')
        lines.append(f'异常反馈数,{summary_stats.get("abnormal", 0)}')
        lines.append(f'异常反馈率,{summary_stats.get("abnormal_rate", 0)}%')
        lines.append(f'高风险回访数,{summary_stats.get("high_risk", 0)}')
        lines.append(f'复约意愿率,{summary_stats.get("rebook_rate", 0)}%')
        lines.append('')
        lines.append('二、满意度评分分布')
        lines.append('评分,数量')
        for sd in score_dist:
            lines.append(f'{sd["satisfaction_score"]}分,{sd["cnt"]}')
        lines.append('')
        lines.append('三、满意度趋势')
        lines.append('时段,回访数,平均满意度,高满意度占比,低满意度占比')
        for t in satisfaction_trend:
            lines.append(f'{t["period_label"]},{t["total"]},{t["avg_score"]},{t["high_ratio"]}%,{t["low_ratio"]}%')
        lines.append('')
        lines.append('四、咨询师服务评分')
        lines.append('咨询师,职称,回访数,平均满意度,复约率,5分,4分,3分,2分,1分')
        for cs in counselor_stats:
            lines.append(f'{cs["name"]},{cs["title"] or ""},{cs["total_surveys"]},{cs["avg_score"]},{cs["rebook_rate"]}%,{cs["score_5"]},{cs["score_4"]},{cs["score_3"]},{cs["score_2"]},{cs["score_1"]}')
        lines.append('')
        lines.append('五、异常反馈占比')
        lines.append('时段,回访数,异常数,异常率,高风险数,高风险率,不复约数,不复约率')
        for a in abnormal_stats:
            lines.append(f'{a["period_label"]},{a["total"]},{a["abnormal_count"]},{a["abnormal_ratio"]}%,{a["high_risk_count"]},{a["high_risk_ratio"]}%,{a["no_rebook_count"]},{a["no_rebook_ratio"]}%')

        csv_content = '\n'.join(lines)
        resp.content_type = 'text/csv; charset=utf-8'
        title = f'回访满意度报表_{start_date}_{end_date}'
        resp.append_header('Content-Disposition', f'attachment; filename="{title}.csv"')
        resp.text = '\ufeff' + csv_content
