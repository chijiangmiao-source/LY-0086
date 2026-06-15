import falcon


class AppException(Exception):
    def __init__(self, message, status_code=400, error_code=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code


class ValidationError(AppException):
    def __init__(self, message='参数校验失败', error_code='VALIDATION_ERROR'):
        super().__init__(message, 400, error_code)


class UnauthorizedError(AppException):
    def __init__(self, message='未登录或会话已过期', error_code='UNAUTHORIZED'):
        super().__init__(message, 401, error_code)


class ForbiddenError(AppException):
    def __init__(self, message='权限不足', error_code='FORBIDDEN'):
        super().__init__(message, 403, error_code)


class NotFoundError(AppException):
    def __init__(self, message='资源不存在', error_code='NOT_FOUND'):
        super().__init__(message, 404, error_code)


class BusinessError(AppException):
    def __init__(self, message='业务处理失败', error_code='BUSINESS_ERROR'):
        super().__init__(message, 400, error_code)


class ConflictError(AppException):
    def __init__(self, message='资源冲突', error_code='CONFLICT'):
        super().__init__(message, 409, error_code)


def handle_exception(req, resp, ex, params):
    if isinstance(ex, AppException):
        resp.status = getattr(falcon, f'HTTP_{ex.status_code}', falcon.HTTP_400)
        resp.media = {
            'error': ex.message,
            'error_code': ex.error_code,
        }
    else:
        resp.status = falcon.HTTP_500
        resp.media = {
            'error': f'服务器内部错误：{str(ex)}',
            'error_code': 'INTERNAL_ERROR',
        }
    resp.complete = True
