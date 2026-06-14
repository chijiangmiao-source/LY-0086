import falcon
from datetime import datetime, date, timedelta
from app.templates import render_template
from app.database import (get_conn, dict_rows, dict_row, get_weekly_report,
                          get_monthly_report, has_permission, calculate_room_utilization)

class AnalyticsPage:
    def on_get(self, req, resp):
        user = req.context.user
        if not has_permission(user['role'], 'view_analytics'):
            resp.status = falcon.HTTP_403
            resp.text = '权限不足'
            return

        report_type = req.get_param('type') or 'week'
        can_export = has_permission(user['role'], 'export_reports')

        if report_type == 'month':
            month_offset = int(req.get_param('month') or 0)
            current_offset = month_offset
            report = get_monthly_report(month_offset)
            prev_offset = month_offset - 1
            next_offset = month_offset + 1
            current_label = report['month_label']
        else:
            week_offset = int(req.get_param('week') or 0)
            current_offset = week_offset
            report = get_weekly_report(week_offset)
            prev_offset = week_offset - 1
            next_offset = week_offset + 1
            current_label = f"{report['week_start']} ~ {report['week_end']}"

        high_risk_slots = report.get('high_risk_slots', [])
        room_usage = report.get('room_usage', [])

        max_usage = max((r['usage_count'] for r in room_usage), default=1)
        for r in room_usage:
            r['usage_pct'] = round(r['usage_count'] / max(max_usage, 1) * 100, 1)
            if 'utilization_rate' not in r:
                r['utilization_rate'] = 0

        if report_type == 'week':
            daily_stats = report.get('daily_stats', [])
            grand_total = report.get('total_appointments', 0)
            grand_noshow = report.get('total_noshow', 0)
            overall_noshow_rate = report.get('overall_noshow_rate', 0)
            grand_checked = sum(d.get('checked', 0) for d in daily_stats)
            overall_attend_rate = round(grand_checked / grand_total * 100, 1) if grand_total > 0 else 0
            weekly_trend = None
        else:
            weekly_trend = report.get('weekly_trend', [])
            grand_total = report.get('total_appointments', 0)
            grand_noshow = report.get('total_noshow', 0)
            overall_noshow_rate = report.get('overall_noshow_rate', 0)
            grand_checked = sum(w.get('checked', 0) for w in weekly_trend)
            overall_attend_rate = round(grand_checked / grand_total * 100, 1) if grand_total > 0 else 0
            daily_stats = None

        time_slots = report.get('time_slots', [])
        max_slot_total = max((ts['total_appointments'] for ts in time_slots), default=1)
        for ts in time_slots:
            ts['bar_pct'] = round(ts['total_appointments'] / max(max_slot_total, 1) * 100, 1)

        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as cnt FROM anonymous_users WHERE risk_level = 'high'")
        high_risk_users = c.fetchone()['cnt']
        c.execute("SELECT COUNT(*) as cnt FROM anonymous_users WHERE risk_level = 'medium'")
        medium_risk_users = c.fetchone()['cnt']
        c.execute("SELECT COUNT(*) as cnt FROM anonymous_users WHERE risk_level = 'low'")
        low_risk_users = c.fetchone()['cnt']
        conn.close()

        resp.content_type = 'text/html; charset=utf-8'
        resp.text = render_template('analytics.html', {
            'user': user,
            'report_type': report_type,
            'current_label': current_label,
            'current_offset': current_offset,
            'prev_offset': prev_offset,
            'next_offset': next_offset,
            'daily_stats': daily_stats,
            'weekly_trend': weekly_trend,
            'grand_total': grand_total,
            'grand_checked': grand_checked,
            'grand_noshow': grand_noshow,
            'overall_noshow_rate': overall_noshow_rate,
            'overall_attend_rate': overall_attend_rate,
            'room_usage': room_usage,
            'time_slots': time_slots,
            'high_risk_slots': high_risk_slots,
            'high_risk_users': high_risk_users,
            'medium_risk_users': medium_risk_users,
            'low_risk_users': low_risk_users,
            'can_export': can_export,
            'risk_warning_count': report.get('risk_warning_count', 0),
            'nav': 'analytics',
            'year': datetime.now().year,
        })

class ReportExportApi:
    def on_get(self, req, resp):
        user = req.context.user
        if not has_permission(user['role'], 'export_reports'):
            resp.status = falcon.HTTP_403
            resp.content_type = 'application/json'
            resp.text = '{"error": "权限不足"}'
            return

        report_type = req.get_param('type') or 'week'

        if report_type == 'month':
            month_offset = int(req.get_param('month') or 0)
            report = get_monthly_report(month_offset)
            title = f"月度分析报告_{report['month_label']}"
        else:
            week_offset = int(req.get_param('week') or 0)
            report = get_weekly_report(week_offset)
            title = f"周度分析报告_{report['week_start']}_{report['week_end']}"

        csv_content = self._generate_csv(report, report_type)

        resp.content_type = 'text/csv; charset=utf-8'
        resp.append_header('Content-Disposition', f'attachment; filename="{title}.csv"')
        resp.text = '\ufeff' + csv_content

    def _generate_csv(self, report, report_type):
        lines = []
        lines.append('校园心理咨询室分析报表')
        lines.append('')

        lines.append('一、总体数据')
        lines.append(f"总预约数,{report.get('total_appointments', 0)}")
        lines.append(f"失约数,{report.get('total_noshow', 0)}")
        lines.append(f"失约率,{report.get('overall_noshow_rate', 0)}%")
        lines.append(f"风险预警数,{report.get('risk_warning_count', 0)}")
        lines.append('')

        lines.append('二、咨询室使用情况')
        lines.append('房间号,房间类型,使用次数,失约数,利用率')
        for r in report.get('room_usage', []):
            lines.append(f"{r.get('room_number', '')},{r.get('room_type', '')},{r.get('usage_count', 0)},{r.get('noshow_count', 0)},{r.get('utilization_rate', 0)}%")
        lines.append('')

        lines.append('三、高风险时段分析')
        lines.append('时段,预约数,失约数,失约率')
        for ts in report.get('high_risk_slots', []):
            lines.append(f"{ts.get('time_label', '')},{ts.get('total_appointments', 0)},{ts.get('noshow_count', 0)},{ts.get('noshow_rate', 0)}%")
        lines.append('')

        if report_type == 'week':
            lines.append('四、每日数据')
            lines.append('日期,预约数,已签到,失约,取消,失约率')
            for d in report.get('daily_stats', []):
                lines.append(f"{d.get('appointment_date', '')},{d.get('total', 0)},{d.get('checked', 0)},{d.get('noshow', 0)},{d.get('cancelled', 0)},{d.get('noshow_rate', 0)}%")
        else:
            lines.append('四、每周趋势')
            lines.append('周次,起始日期,预约数,已签到,失约,失约率')
            for w in report.get('weekly_trend', []):
                lines.append(f"{w.get('week_num', '')},{w.get('week_start', '')},{w.get('total', 0)},{w.get('checked', 0)},{w.get('noshow', 0)},{w.get('noshow_rate', 0)}%")

        return '\n'.join(lines)
