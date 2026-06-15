import falcon
from app.database import has_permission, get_role_permissions
from app.utils.exceptions import UnauthorizedError, ForbiddenError


class PermissionService:

    @staticmethod
    def get_current_user(req):
        user = getattr(req.context, 'user', None)
        if not user:
            raise UnauthorizedError()
        return user

    @staticmethod
    def check_login(req):
        user = getattr(req.context, 'user', None)
        if not user:
            raise UnauthorizedError()
        return user

    @staticmethod
    def has_permission(role, permission):
        return has_permission(role, permission)

    @staticmethod
    def require_permission(req, permission):
        user = PermissionService.check_login(req)
        if not has_permission(user['role'], permission):
            raise ForbiddenError()
        return user

    @staticmethod
    def can(req, permission):
        user = getattr(req.context, 'user', None)
        if not user:
            return False
        return has_permission(user['role'], permission)

    @staticmethod
    def get_permissions(role):
        return get_role_permissions(role)


def require_permission_decorator(permission):
    def decorator(func):
        def wrapper(self, req, resp, *args, **kwargs):
            PermissionService.require_permission(req, permission)
            return func(self, req, resp, *args, **kwargs)
        return wrapper
    return decorator
