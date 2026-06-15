import falcon
import json
from datetime import datetime, date, timedelta
from app.templates import render_template
from app.database import (
    get_conn, dict_rows, dict_row, has_permission,
    get_counselor_quality_comparison, get_rebook_analysis,
    get_quality_overview,
)
from config import FOLLOWUP_DEFAULT_DAYS_RANGE, REBOOK_ANALYSIS_DAYS

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

class QualityComparisonPage:
    def on_get(self, req, resp):
        user = req.context.user
        if not has_permission(user['role'], 'view_quality_comparison'):
            resp.status = falcon.HTTP_403
            resp.text = '权限不足'
            return

        days_range = int(req.get_param('days') or FOLLOWUP_DEFAULT_DAYS_RANGE)
        end_date = date.today().isoformat()
        start_date = (date.today() - timedelta(days=days_range)).isoformat()

        counselors = get_counselor_quality_comparison(start_date, end_date)
        overview = get_quality_overview(start_date, end_date)

        max_satisfaction = max((c['avg_satisfaction'] for c in counselors), default=1)
        for c in counselors:
            c['bar_width'] = round(c['avg_satisfaction'] / max(max_satisfaction, 1) * 100, 1)

        resp.content_type = 'text/html; charset=utf-8'
        resp.text = render_template('quality_comparison.html', {
            'user': user,
            'counselors': counselors,
            'overview': overview,
            'start_date': start_date,
            'end_date': end_date,
            'days_range': days_range,
            'nav': 'quality',
            'year': datetime.now().year,
        })

class RebookAnalysisPage:
    def on_get(self, req, resp):
        user = req.context.user
        if not has_permission(user['role'], 'view_rebook_analysis'):
            resp.status = falcon.HTTP_403
            resp.text = '权限不足'
            return

        days_range = int(req.get_param('days') or REBOOK_ANALYSIS_DAYS)
        end_date = date.today().isoformat()
        start_date = (date.today() - timedelta(days=days_range)).isoformat()

        analysis = get_rebook_analysis(start_date, end_date)

        max_count = max((d['count'] for d in analysis.get('interval_distribution', [])), default=1)
        for d in analysis.get('interval_distribution', []):
            d['bar_width'] = round(d['count'] / max(max_count, 1) * 100, 1)

        max_clients = max((c['total_clients'] for c in analysis.get('counselor_rebook', [])), default=1)
        for c in analysis.get('counselor_rebook', []):
            c['bar_width'] = round(c['total_clients'] / max(max_clients, 1) * 100, 1)

        resp.content_type = 'text/html; charset=utf-8'
        resp.text = render_template('rebook_analysis.html', {
            'user': user,
            'analysis': analysis,
            'start_date': start_date,
            'end_date': end_date,
            'days_range': days_range,
            'nav': 'rebook',
            'year': datetime.now().year,
        })

class QualityAnalyticsPage:
    def on_get(self, req, resp):
        user = req.context.user
        if not has_permission(user['role'], 'view_quality_comparison'):
            resp.status = falcon.HTTP_403
            resp.text = '权限不足'
            return

        days_range = int(req.get_param('days') or FOLLOWUP_DEFAULT_DAYS_RANGE)
        end_date = date.today().isoformat()
        start_date = (date.today() - timedelta(days=days_range)).isoformat()

        counselors = get_counselor_quality_comparison(start_date, end_date)
        rebook = get_rebook_analysis(start_date, end_date)
        overview = get_quality_overview(start_date, end_date)

        max_satisfaction = max((c['avg_satisfaction'] for c in counselors), default=1)
        for c in counselors:
            c['bar_width'] = round(c['avg_satisfaction'] / max(max_satisfaction, 1) * 100, 1)

        resp.content_type = 'text/html; charset=utf-8'
        resp.text = render_template('quality_analytics.html', {
            'user': user,
            'counselors': counselors,
            'rebook': rebook,
            'overview': overview,
            'start_date': start_date,
            'end_date': end_date,
            'days_range': days_range,
            'nav': 'quality_analytics',
            'year': datetime.now().year,
        })

class QualityExportApi:
    def on_get(self, req, resp):
        if not require_permission(req, resp, 'view_quality_comparison'):
            resp.status = falcon.HTTP_403
            resp.media = {'error': '权限不足'}
            return

        days_range = int(req.get_param('days') or FOLLOWUP_DEFAULT_DAYS_RANGE)
        end_date = date.today().isoformat()
        start_date = (date.today() - timedelta(days=days_range)).isoformat()

        counselors = get_counselor_quality_comparison(start_date, end_date)

        lines = []
        lines.append('咨询师服务质量对比报表')
        lines.append(f'统计周期：{start_date} ~ {end_date}')
        lines.append('')
        lines.append('咨询师,职称,咨询量,到场率,回访量,平均满意度,满意度,复约率,异常率,人均咨询次数')
        for c in counselors:
            lines.append(
                f'{c.get("name","")},{c.get("title","") or ""},{c.get("total_appointments",0)},'
                f'{c.get("attendance_rate",0)}%,{c.get("followup_count",0)},'
                f'{c.get("avg_satisfaction",0)},{c.get("satisfaction_rate",0)}%,'
                f'{c.get("rebook_rate",0)}%,{c.get("abnormal_rate",0)}%,'
                f'{c.get("avg_appts_per_client",0)}'
            )

        csv_content = '\n'.join(lines)
        resp.content_type = 'text/csv; charset=utf-8'
        title = f'咨询师质量对比_{start_date}_{end_date}'
        resp.append_header('Content-Disposition', f'attachment; filename="{title}.csv"')
        resp.text = '\ufeff' + csv_content

class RebookExportApi:
    def on_get(self, req, resp):
        if not require_permission(req, resp, 'view_rebook_analysis'):
            resp.status = falcon.HTTP_403
            resp.media = {'error': '权限不足'}
            return

        days_range = int(req.get_param('days') or REBOOK_ANALYSIS_DAYS)
        end_date = date.today().isoformat()
        start_date = (date.today() - timedelta(days=days_range)).isoformat()

        analysis = get_rebook_analysis(start_date, end_date)

        lines = []
        lines.append('复约转化分析报表')
        lines.append(f'统计周期：{start_date} ~ {end_date}')
        lines.append('')
        lines.append('一、总体概况')
        lines.append(f'总用户数,{analysis.get("total_users",0)}')
        lines.append(f'复约用户数,{analysis.get("repeat_users",0)}')
        lines.append(f'复约率,{analysis.get("rebook_rate",0)}%')
        lines.append(f'总咨询量,{analysis.get("total_appointments",0)}')
        lines.append(f'到场咨询量,{analysis.get("attended_appointments",0)}')
        lines.append(f'平均复约间隔,{analysis.get("avg_interval_days",0)}天')
        lines.append('')
        lines.append('二、咨询师复约情况')
        lines.append('咨询师,总客户数,复购客户数,复购率,转介客户数,转介率')
        for c in analysis.get('counselor_rebook', []):
            lines.append(
                f'{c.get("name","")},{c.get("total_clients",0)},'
                f'{c.get("returning_clients",0)},{c.get("return_rate",0)}%,'
                f'{c.get("transferred_clients",0)},{c.get("transfer_rate",0)}%'
            )
        lines.append('')
        lines.append('三、月度趋势')
        lines.append('月份,新客户数,回头客数,新客户占比,回头客占比')
        for m in analysis.get('monthly_trend', []):
            lines.append(
                f'{m.get("month","")},{m.get("new_clients",0)},'
                f'{m.get("returning_clients",0)},{m.get("new_ratio",0)}%,{m.get("return_ratio",0)}%'
            )

        csv_content = '\n'.join(lines)
        resp.content_type = 'text/csv; charset=utf-8'
        title = f'复约转化分析_{start_date}_{end_date}'
        resp.append_header('Content-Disposition', f'attachment; filename="{title}.csv"')
        resp.text = '\ufeff' + csv_content
