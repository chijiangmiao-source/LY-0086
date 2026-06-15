from datetime import datetime, timedelta, date
from app.database import (
    get_conn, dict_rows, dict_row,
    get_followup_summary_stats, get_satisfaction_trend,
    get_counselor_satisfaction_distribution, get_abnormal_feedback_stats,
    get_supervision_summary, get_high_risk_tracking_summary,
)
from app.utils.helpers import now_str


class StatisticsService:

    @staticmethod
    def calculate_rate(numerator, denominator, precision=1):
        if not denominator or denominator <= 0:
            return 0
        return round(numerator / denominator * 100, precision)

    @staticmethod
    def calculate_bar_percentage(value, max_value, precision=1):
        if not max_value or max_value <= 0:
            return 0
        return round(value / max(max_value, 1) * 100, precision)

    @staticmethod
    def calculate_noshow_rate(total, noshow):
        return StatisticsService.calculate_rate(noshow, total)

    @staticmethod
    def calculate_cancel_rate(total, cancelled):
        return StatisticsService.calculate_rate(cancelled, total)

    @staticmethod
    def calculate_attend_rate(total, checked):
        return StatisticsService.calculate_rate(checked, total)

    @staticmethod
    def calculate_satisfaction_rate(total_surveys, satisfied_count):
        return StatisticsService.calculate_rate(satisfied_count, total_surveys)

    @staticmethod
    def enrich_trend_with_bar(items, total_key='total'):
        max_total = max((t.get(total_key, 0) for t in items), default=1)
        for t in items:
            t['bar_pct'] = StatisticsService.calculate_bar_percentage(t.get(total_key, 0), max_total)
        return items

    @staticmethod
    def get_followup_statistics(start_date, end_date, period='week'):
        summary_stats, score_dist = get_followup_summary_stats(start_date, end_date)
        satisfaction_trend = get_satisfaction_trend(start_date, end_date, period)
        counselor_stats = get_counselor_satisfaction_distribution(start_date, end_date)
        abnormal_stats = get_abnormal_feedback_stats(start_date, end_date, period)
        satisfaction_trend = StatisticsService.enrich_trend_with_bar(satisfaction_trend)
        abnormal_stats = StatisticsService.enrich_trend_with_bar(abnormal_stats)
        return {
            'summary_stats': summary_stats,
            'score_dist': score_dist,
            'satisfaction_trend': satisfaction_trend,
            'counselor_stats': counselor_stats,
            'abnormal_stats': abnormal_stats,
        }

    @staticmethod
    def get_supervision_statistics(user_id=None):
        return get_supervision_summary(user_id=user_id)

    @staticmethod
    def get_high_risk_statistics():
        return get_high_risk_tracking_summary()

    @staticmethod
    def calculate_date_range(days_range=None):
        from config import FOLLOWUP_DEFAULT_DAYS_RANGE
        if days_range is None:
            days_range = FOLLOWUP_DEFAULT_DAYS_RANGE
        end_date = date.today().isoformat()
        start_date = (date.today() - timedelta(days=days_range)).isoformat()
        return start_date, end_date
