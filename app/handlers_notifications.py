import falcon
from datetime import datetime, date, timedelta
from app.templates import render_template
from app.database import (get_conn, dict_rows, dict_row,
                          get_user_notifications, get_unread_notification_count,
                          mark_notification_read, has_permission)

class NotificationsPage:
    def on_get(self, req, resp):
        user = req.context.user
        if not has_permission(user['role'], 'view_notifications'):
            resp.status = falcon.HTTP_403
            resp.text = '权限不足'
            return

        unread_only = req.get_param('unread') == '1'
        notifs = get_user_notifications(user['user_id'], unread_only=unread_only, limit=50)

        type_labels = {
            'risk_warning': '风险预警',
            'checkin_anomaly': '签到异常',
            'appointment_reminder': '预约提醒',
            'system': '系统通知',
        }

        for n in notifs:
            n['type_label'] = type_labels.get(n['notification_type'], n['notification_type'])

        unread_count = get_unread_notification_count(user['user_id'])

        resp.content_type = 'text/html; charset=utf-8'
        resp.text = render_template('notifications.html', {
            'user': user,
            'notifications': notifs,
            'unread_count': unread_count,
            'unread_only': unread_only,
            'type_labels': type_labels,
            'nav': 'notifications',
            'year': datetime.now().year,
        })

class NotificationsApi:
    def on_get(self, req, resp):
        user = req.context.user
        if not has_permission(user['role'], 'view_notifications'):
            resp.status = falcon.HTTP_403
            resp.media = {'error': '权限不足'}
            return

        unread_only = req.get_param('unread') == '1'
        limit = int(req.get_param('limit') or 20)
        notifs = get_user_notifications(user['user_id'], unread_only=unread_only, limit=limit)
        unread_count = get_unread_notification_count(user['user_id'])

        resp.media = {
            'notifications': notifs,
            'unread_count': unread_count,
        }

class MarkNotificationReadApi:
    def on_post(self, req, resp):
        user = req.context.user
        if not has_permission(user['role'], 'view_notifications'):
            resp.status = falcon.HTTP_403
            resp.media = {'error': '权限不足'}
            return

        form = req.get_media() or {}
        notification_id = form.get('notification_id')
        mark_all = form.get('mark_all') == '1'

        if mark_all:
            conn = get_conn()
            c = conn.cursor()
            c.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0", (user['user_id'],))
            conn.commit()
            conn.close()
        elif notification_id:
            mark_notification_read(notification_id, user['user_id'])

        resp.media = {'success': True}

class NotificationsBadgePartial:
    def on_get(self, req, resp):
        user = req.context.user
        if not user or not has_permission(user['role'], 'view_notifications'):
            resp.text = ''
            return
        count = get_unread_notification_count(user['user_id'])
        if count > 0:
            resp.content_type = 'text/html; charset=utf-8'
            resp.text = f'<span class="badge bg-danger" style="font-size:10px;">{count}</span>'
        else:
            resp.text = ''
