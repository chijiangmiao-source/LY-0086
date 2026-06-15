from app.database import (
    get_conn, create_notification,
)
from app.utils.helpers import now_str


NOTIFICATION_TYPE_RISK_WARNING = 'risk_warning'
NOTIFICATION_TYPE_CHECKIN_ANOMALY = 'checkin_anomaly'
NOTIFICATION_TYPE_APPOINTMENT_REMINDER = 'appointment_reminder'
NOTIFICATION_TYPE_SUPERVISION = 'supervision'
NOTIFICATION_TYPE_FOLLOWUP_ALERT = 'followup_alert'
NOTIFICATION_TYPE_SYSTEM = 'system'


ROLES_ADMIN_INTERVENTION = ['admin', 'intervention']
ROLES_ADMIN_INTERVENTION_STAFF = ['admin', 'intervention', 'staff']


class NotificationService:

    @staticmethod
    def send_to_user(user_id, notification_type, title, content, related_appointment_id=None,
                     related_supervision_task_id=None):
        conn = get_conn()
        c = conn.cursor()
        params = [user_id, notification_type, title, content, related_appointment_id]
        extra_col = ''
        extra_val = []
        if related_supervision_task_id is not None:
            extra_col = ', related_supervision_task_id'
            extra_val = [related_supervision_task_id]
        c.execute(f"""INSERT INTO notifications 
                     (user_id, notification_type, title, content, related_appointment_id{extra_col})
                     VALUES (?, ?, ?, ?, ?{', ?' if extra_val else ''})""",
                  params + extra_val)
        conn.commit()
        conn.close()
        return c.lastrowid

    @staticmethod
    def send_to_roles(roles, notification_type, title, content, related_appointment_id=None,
                      related_supervision_task_id=None):
        conn = get_conn()
        c = conn.cursor()
        placeholders = ','.join(['?' for _ in roles])
        params = [notification_type, title, content, related_appointment_id]
        extra_col = ''
        extra_val = []
        if related_supervision_task_id is not None:
            extra_col = ', related_supervision_task_id'
            extra_val = [related_supervision_task_id]
        c.execute(f"""INSERT INTO notifications (user_id, notification_type, title, content, related_appointment_id{extra_col})
                     SELECT u.id, ?, ?, ?, ?{', ?' if extra_val else ''}
                     FROM users u 
                     WHERE u.role IN ({placeholders})""",
                  params + extra_val + list(roles))
        conn.commit()
        conn.close()

    @staticmethod
    def send_risk_warning(title, content, related_appointment_id=None):
        NotificationService.send_to_roles(
            ROLES_ADMIN_INTERVENTION,
            NOTIFICATION_TYPE_RISK_WARNING,
            title,
            content,
            related_appointment_id
        )

    @staticmethod
    def send_checkin_anomaly(title, content, related_appointment_id=None):
        NotificationService.send_to_roles(
            ROLES_ADMIN_INTERVENTION_STAFF,
            NOTIFICATION_TYPE_CHECKIN_ANOMALY,
            title,
            content,
            related_appointment_id
        )

    @staticmethod
    def send_followup_alert(title, content, related_appointment_id=None):
        NotificationService.send_to_roles(
            ROLES_ADMIN_INTERVENTION,
            NOTIFICATION_TYPE_FOLLOWUP_ALERT,
            title,
            content,
            related_appointment_id
        )

    @staticmethod
    def send_supervision_notification(user_id, title, content, related_appointment_id=None,
                                       related_supervision_task_id=None):
        NotificationService.send_to_user(
            user_id,
            NOTIFICATION_TYPE_SUPERVISION,
            title,
            content,
            related_appointment_id,
            related_supervision_task_id
        )
