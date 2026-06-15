import re
from datetime import datetime, date, timedelta
from config import CHECKIN_WINDOW_MINUTES_BEFORE, CHECKIN_WINDOW_MINUTES_AFTER


ANONYMOUS_CODE_PATTERN = re.compile(r'^[A-Za-z0-9_-]{4,32}$')


def validate_anonymous_code(code):
    if not code:
        return False, '匿名识别码不能为空'
    if not ANONYMOUS_CODE_PATTERN.match(code):
        return False, '匿名识别码格式不正确，需4-32位字母数字下划线'
    return True, None


def validate_date_str(date_str, fmt='%Y-%m-%d'):
    if not date_str:
        return False, '日期不能为空'
    try:
        datetime.strptime(date_str, fmt)
        return True, None
    except (ValueError, TypeError):
        return False, f'日期格式不正确，需为{fmt}格式'


def validate_required(value, field_name='参数'):
    if value is None or (isinstance(value, str) and not value.strip()):
        return False, f'{field_name}不能为空'
    return True, None


def validate_int(value, min_val=None, max_val=None, field_name='参数'):
    try:
        num = int(value)
        if min_val is not None and num < min_val:
            return False, f'{field_name}不能小于{min_val}'
        if max_val is not None and num > max_val:
            return False, f'{field_name}不能大于{max_val}'
        return True, num
    except (ValueError, TypeError):
        return False, f'{field_name}必须为有效整数'


def mask_anonymous_code(code):
    if not code:
        return '***'
    if len(code) > 6:
        return code[:4] + '***' + code[-2:]
    return code[:3] + '***'


def calculate_checkin_info(appointment_date, start_time, end_time,
                           checkin_status, no_show_marked, checkin_time=None):
    result = {
        'can_checkin': False,
        'can_mark_noshow': False,
        'is_late': False,
        'late_minutes': 0,
    }
    apt_dt_str = f"{appointment_date} {start_time}"
    try:
        apt_dt = datetime.strptime(apt_dt_str, '%Y-%m-%d %H:%M')
        now = datetime.now()
        before = apt_dt - timedelta(minutes=CHECKIN_WINDOW_MINUTES_BEFORE)
        after = apt_dt + timedelta(minutes=CHECKIN_WINDOW_MINUTES_AFTER)
        result['can_checkin'] = (checkin_status == 'pending' and no_show_marked == 0
                                  and before <= now <= after)
        result['can_mark_noshow'] = (checkin_status == 'pending' and no_show_marked == 0
                                      and now > after)
        if checkin_status == 'checked_in' and checkin_time:
            checkin_dt = datetime.strptime(checkin_time, '%Y-%m-%d %H:%M:%S')
            late_delta = checkin_dt - apt_dt
            late_minutes = int(late_delta.total_seconds() / 60)
            result['is_late'] = late_minutes > 0
            result['late_minutes'] = max(0, late_minutes)
        else:
            result['is_late'] = (checkin_status == 'pending' and no_show_marked == 0
                                  and now > apt_dt)
            result['late_minutes'] = 0
    except Exception:
        pass
    return result


def parse_satisfaction_score(score):
    if score is None:
        return True, None
    try:
        score_int = int(score)
        if score_int < 1 or score_int > 5:
            return False, '满意度评分须为1-5的整数'
        return True, score_int
    except (ValueError, TypeError):
        return False, '满意度评分须为1-5的整数'
