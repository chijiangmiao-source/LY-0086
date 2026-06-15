import falcon
from datetime import datetime, date, timedelta
from app.templates import render_template
from app.services.followup_service import FollowupService
from app.services.permission_service import PermissionService
from app.services.statistics_service import StatisticsService
from app.utils.response import set_html_response, set_json_response, set_csv_response, set_success_response
from app.utils.exceptions import AppException, handle_exception
from config import FOLLOWUP_DEFAULT_DAYS_RANGE


class FollowupPage:
    def on_get(self, req, resp):
        user = PermissionService.require_permission(req, 'view_followup')
        can_manage = PermissionService.can(req, 'manage_followup')

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

        surveys = FollowupService.get_surveys(filters)
        counselors = FollowupService.get_counselors_for_filter()

        set_html_response(resp, render_template('followup.html', {
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
        }))


class FollowupSurveyPage:
    def on_get(self, req, resp):
        anonymous_code = req.get_param('code') or ''
        if not anonymous_code:
            set_html_response(resp, render_template('followup_survey.html', {
                'error': '请提供匿名编码',
                'anonymous_code': '',
                'appointments': [],
                'questions': [],
                'selected_appointment': None,
                'year': datetime.now().year,
            }))
            return

        appointments = FollowupService.get_eligible_appointments(anonymous_code)
        questions = FollowupService.get_active_questions_with_parsed_options()

        set_html_response(resp, render_template('followup_survey.html', {
            'error': None,
            'anonymous_code': anonymous_code,
            'appointments': appointments,
            'questions': questions,
            'selected_appointment': None,
            'year': datetime.now().year,
        }))


class FollowupSurveySubmitApi:
    def on_post(self, req, resp):
        try:
            form = req.get_media() or {}
            appointment_id = form.get('appointment_id')
            anonymous_code = form.get('anonymous_code', '').strip()
            satisfaction_score = form.get('satisfaction_score')
            rebook_willingness = form.get('rebook_willingness', 'undecided')
            responses = form.get('responses') or {}
            comment = (form.get('comment') or '').strip()

            result = FollowupService.submit_survey(
                appointment_id=appointment_id,
                anonymous_code=anonymous_code,
                satisfaction_score=satisfaction_score,
                rebook_willingness=rebook_willingness,
                responses=responses,
                comment=comment,
            )
            resp.media = {'success': True, **result}
        except AppException as e:
            handle_exception(req, resp, e, None)


class FollowupDetailApi:
    def on_get(self, req, resp, survey_id):
        try:
            PermissionService.require_permission(req, 'view_followup')
            survey = FollowupService.get_survey_detail(survey_id)
            resp.media = survey
        except AppException as e:
            handle_exception(req, resp, e, None)


class FollowupMarkAbnormalApi:
    def on_post(self, req, resp):
        try:
            PermissionService.require_permission(req, 'manage_followup')
            form = req.get_media() or {}
            survey_id = form.get('survey_id')
            is_abnormal = form.get('is_abnormal', 1)
            abnormal_reason = (form.get('abnormal_reason') or '').strip()
            is_high_risk = form.get('is_high_risk')
            high_risk_reason = (form.get('high_risk_reason') or '').strip()

            FollowupService.mark_abnormal(survey_id, is_abnormal, abnormal_reason, is_high_risk, high_risk_reason)
            resp.media = {'success': True}
        except AppException as e:
            handle_exception(req, resp, e, None)


class FollowupQuestionsApi:
    def on_get(self, req, resp):
        try:
            PermissionService.require_permission(req, 'manage_followup')
            questions = FollowupService.get_all_questions()
            resp.media = {'questions': questions}
        except AppException as e:
            handle_exception(req, resp, e, None)

    def on_post(self, req, resp):
        try:
            PermissionService.require_permission(req, 'manage_followup')
            form = req.get_media() or {}
            question_text = (form.get('question_text') or '').strip()
            question_type = form.get('question_type') or 'text'
            options = form.get('options') or None
            sort_order = form.get('sort_order') or 0

            qid = FollowupService.add_question(question_text, question_type, options, sort_order)
            resp.media = {'success': True, 'question_id': qid}
        except AppException as e:
            handle_exception(req, resp, e, None)


class FollowupQuestionUpdateApi:
    def on_post(self, req, resp, question_id):
        try:
            PermissionService.require_permission(req, 'manage_followup')
            form = req.get_media() or {}
            FollowupService.update_question(question_id, **form)
            resp.media = {'success': True}
        except AppException as e:
            handle_exception(req, resp, e, None)


class FollowupAnalyticsPage:
    def on_get(self, req, resp):
        user = PermissionService.require_permission(req, 'view_followup_analytics')

        days_range = int(req.get_param('days') or FOLLOWUP_DEFAULT_DAYS_RANGE)
        period = req.get_param('period') or 'week'
        end_date = date.today().isoformat()
        start_date = (date.today() - timedelta(days=days_range)).isoformat()

        stats = StatisticsService.get_followup_statistics(start_date, end_date, period)
        high_risk_warnings = FollowupService.get_high_risk_warnings(20)

        set_html_response(resp, render_template('followup_analytics.html', {
            'user': user,
            'start_date': start_date,
            'end_date': end_date,
            'days_range': days_range,
            'period': period,
            'summary_stats': stats['summary_stats'],
            'score_dist': stats['score_dist'],
            'satisfaction_trend': stats['satisfaction_trend'],
            'counselor_stats': stats['counselor_stats'],
            'abnormal_stats': stats['abnormal_stats'],
            'high_risk_warnings': high_risk_warnings,
            'nav': 'followup_analytics',
            'year': datetime.now().year,
        }))


class FollowupAnalyticsExportApi:
    def on_get(self, req, resp):
        try:
            PermissionService.require_permission(req, 'view_followup_analytics')

            days_range = int(req.get_param('days') or FOLLOWUP_DEFAULT_DAYS_RANGE)
            period = req.get_param('period') or 'week'
            end_date = date.today().isoformat()
            start_date = (date.today() - timedelta(days=days_range)).isoformat()

            stats = StatisticsService.get_followup_statistics(start_date, end_date, period)
            summary_stats = stats['summary_stats']
            score_dist = stats['score_dist']
            satisfaction_trend = stats['satisfaction_trend']
            counselor_stats = stats['counselor_stats']
            abnormal_stats = stats['abnormal_stats']

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
            title = f'回访满意度报表_{start_date}_{end_date}'
            set_csv_response(resp, csv_content, title)
        except AppException as e:
            handle_exception(req, resp, e, None)
