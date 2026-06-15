import json


def safe_json_loads(s, default=None):
    if s is None:
        return default if default is not None else {}
    if isinstance(s, (dict, list)):
        return s
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError, ValueError):
        return default if default is not None else {}


def safe_json_dumps(obj, ensure_ascii=False):
    if obj is None:
        return None
    if isinstance(obj, str):
        return obj
    try:
        return json.dumps(obj, ensure_ascii=ensure_ascii)
    except (TypeError, ValueError):
        return None


def parse_options_list(options):
    if options is None:
        return []
    if isinstance(options, list):
        return options
    if isinstance(options, str):
        return safe_json_loads(options, [])
    return []


def now_str(fmt='%Y-%m-%d %H:%M:%S'):
    from datetime import datetime
    return datetime.now().strftime(fmt)


def today_str():
    from datetime import date
    return date.today().isoformat()


def clean_str(s):
    if s is None:
        return ''
    return str(s).strip()
