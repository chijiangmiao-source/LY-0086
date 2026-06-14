import falcon
import secrets
import hashlib
from datetime import datetime, timedelta
from config import SECRET_KEY, SESSION_COOKIE_NAME
from app.database import get_conn, dict_row

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generate_session_token():
    return secrets.token_urlsafe(48)

def create_session(user_id):
    conn = get_conn()
    c = conn.cursor()
    token = generate_session_token()
    expires = (datetime.now() + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
    c.execute("INSERT INTO sessions (session_token, user_id, expires_at) VALUES (?,?,?)",
              (token, user_id, expires))
    conn.commit()
    conn.close()
    return token, expires

def get_user_by_token(token):
    if not token:
        return None
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT s.*, u.username, u.role, u.real_name 
                 FROM sessions s JOIN users u ON s.user_id = u.id 
                 WHERE s.session_token = ? AND s.expires_at > ?""",
              (token, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    row = c.fetchone()
    conn.close()
    return dict_row(row)

def destroy_session(token):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM sessions WHERE session_token = ?", (token,))
    conn.commit()
    conn.close()

def verify_user(username, password):
    conn = get_conn()
    c = conn.cursor()
    pw_hash = hash_password(password)
    c.execute("SELECT * FROM users WHERE username = ? AND password_hash = ?", (username, pw_hash))
    row = c.fetchone()
    conn.close()
    return dict_row(row)

class AuthMiddleware:
    def __init__(self, exempt_paths=None):
        self.exempt = exempt_paths or []
        self.exempt_prefixes = ['/static/', '/login', '/api/public', '/anonymous', '/api/anonymous', '/api/followup/submit']

    def _is_exempt(self, path):
        if path in self.exempt:
            return True
        for prefix in self.exempt_prefixes:
            if path.startswith(prefix):
                return True
        return False

    def process_request(self, req, resp):
        if self._is_exempt(req.path):
            req.context.user = None
            return
        token = req.get_cookie_values(SESSION_COOKIE_NAME)
        token = token[0] if token else None
        if not token:
            auth_header = req.get_header('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                token = auth_header[7:]
        user = get_user_by_token(token)
        if not user:
            if req.path.startswith('/api/'):
                resp.status = falcon.HTTP_401
                resp.media = {'error': '未登录或会话已过期'}
                resp.complete = True
            else:
                raise falcon.HTTPFound('/login')
            return
        req.context.user = user
        req.context.session_token = token

    def process_response(self, req, resp, resource, req_succeeded):
        pass
