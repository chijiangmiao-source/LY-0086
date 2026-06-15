import falcon


def success(data=None, message='操作成功', **kwargs):
    result = {
        'success': True,
        'message': message,
    }
    if data is not None:
        result['data'] = data
    result.update(kwargs)
    return result


def error(message='操作失败', error_code='ERROR', status_code=400):
    return {
        'success': False,
        'error': message,
        'error_code': error_code,
        '_status_code': status_code,
    }


def set_json_response(resp, data, status_code=200):
    resp.status = getattr(falcon, f'HTTP_{status_code}', falcon.HTTP_200)
    resp.content_type = 'application/json'
    resp.media = data


def set_success_response(resp, data=None, message='操作成功', **kwargs):
    set_json_response(resp, success(data, message, **kwargs), 200)


def set_error_response(resp, message='操作失败', error_code='ERROR', status_code=400):
    set_json_response(resp, error(message, error_code, status_code), status_code)


def set_html_response(resp, html_content, status_code=200):
    resp.status = getattr(falcon, f'HTTP_{status_code}', falcon.HTTP_200)
    resp.content_type = 'text/html; charset=utf-8'
    resp.text = html_content


def set_csv_response(resp, csv_content, filename):
    resp.content_type = 'text/csv; charset=utf-8'
    resp.append_header('Content-Disposition', f'attachment; filename="{filename}.csv"')
    resp.text = '\ufeff' + csv_content
