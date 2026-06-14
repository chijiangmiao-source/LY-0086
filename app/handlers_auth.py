import falcon
import json
from datetime import datetime
from app.auth import verify_user, create_session, destroy_session
from app.templates import render_template
from config import SESSION_COOKIE_NAME

class LoginPage:
    def on_get(self, req, resp):
        msg = req.get_param('msg') or ''
        resp.content_type = 'text/html; charset=utf-8'
        resp.text = render_template('login.html', {'message': msg, 'year': datetime.now().year})

class LoginAction:
    def on_post(self, req, resp):
        form = req.get_media()
        if isinstance(form, dict):
            username = form.get('username', '')
            password = form.get('password', '')
        else:
            username = req.get_param('username') or ''
            password = req.get_param('password') or ''
        user = verify_user(username.strip(), password)
        if not user:
            if req.path.startswith('/api/'):
                resp.status = falcon.HTTP_401
                resp.media = {'error': '用户名或密码错误'}
                return
            resp.status = falcon.HTTP_302
            resp.set_header('Location', '/login?msg=用户名或密码错误')
            return
        token, expires = create_session(user['id'])
        max_age = 8 * 3600
        resp.set_cookie(SESSION_COOKIE_NAME, token, path='/', max_age=max_age, http_only=True)
        if req.path.startswith('/api/'):
            resp.media = {'token': token, 'user': {'id': user['id'], 'username': user['username'], 'role': user['role'], 'real_name': user['real_name']}}
            return
        resp.status = falcon.HTTP_302
        resp.set_header('Location', '/')

class LogoutAction:
    def on_get(self, req, resp):
        token = req.get_cookie_values(SESSION_COOKIE_NAME)
        token = token[0] if token else None
        if token:
            destroy_session(token)
        resp.unset_cookie(SESSION_COOKIE_NAME, path='/')
        resp.status = falcon.HTTP_302
        resp.set_header('Location', '/login')
