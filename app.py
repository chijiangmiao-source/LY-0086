import os
import falcon
from wsgiref import simple_server
from waitress import serve

from config import BASE_DIR
from app.database import init_db
from app.auth import AuthMiddleware
from app.handlers_auth import LoginPage, LoginAction, LogoutAction
from app.handlers_dashboard import Dashboard
from app.handlers_rooms import RoomsPage, RoomFormPartial, RoomApi
from app.handlers_counselors import CounselorsPage, CounselorApi, SchedulesPage, ScheduleApi
from app.handlers_appointments import (AnonymousBookPage, AnonymousBookCheck, AnonymousBookSubmit,
                                       AppointmentsPage)
from app.handlers_checkin import (CheckinApi, MarkNoShowApi, CancelAppointmentApi,
                                   InterventionsPage, LiftCooldownApi, InterventionRemarkApi)
from app.handlers_analytics import AnalyticsPage, ReportExportApi
from app.handlers_risk import RiskWarningsPage, RiskUsersPage, ResolveWarningApi
from app.handlers_notifications import (NotificationsPage, NotificationsApi,
                                          MarkNotificationReadApi, NotificationsBadgePartial)
from app.handlers_followup import (FollowupPage, FollowupSurveyPage, FollowupSurveySubmitApi,
                                    FollowupDetailApi, FollowupMarkAbnormalApi,
                                    FollowupQuestionsApi, FollowupQuestionUpdateApi,
                                    FollowupAnalyticsPage, FollowupAnalyticsExportApi)

def create_app():
    init_db()

    static_dir = os.path.join(BASE_DIR, 'static')

    app = falcon.App(
        middleware=[AuthMiddleware()],
        cors_enable=True,
    )

    app.add_static_route('/static', static_dir)

    app.add_route('/', Dashboard())

    app.add_route('/login', LoginPage())
    app.add_route('/login/submit', LoginAction())
    app.add_route('/api/login', LoginAction())
    app.add_route('/logout', LogoutAction())
    app.add_route('/api/logout', LogoutAction())

    app.add_route('/rooms', RoomsPage())
    app.add_route('/rooms/form', RoomFormPartial())
    app.add_route('/rooms/form/{room_id:int}', RoomFormPartial())
    app.add_route('/api/rooms', RoomApi())
    app.add_route('/api/rooms/{room_id:int}', RoomApi())

    app.add_route('/counselors', CounselorsPage())
    app.add_route('/api/counselors', CounselorApi())
    app.add_route('/api/counselors/{counselor_id:int}', CounselorApi())

    app.add_route('/schedules', SchedulesPage())
    app.add_route('/api/schedules', ScheduleApi())
    app.add_route('/api/schedules/{schedule_id:int}', ScheduleApi())

    app.add_route('/anonymous/book', AnonymousBookPage())
    app.add_route('/api/anonymous/book/check', AnonymousBookCheck())
    app.add_route('/api/anonymous/book/submit', AnonymousBookSubmit())

    app.add_route('/appointments', AppointmentsPage())
    app.add_route('/api/checkin', CheckinApi())
    app.add_route('/api/noshow', MarkNoShowApi())
    app.add_route('/api/cancel', CancelAppointmentApi())

    app.add_route('/interventions', InterventionsPage())
    app.add_route('/api/cooldown/lift', LiftCooldownApi())
    app.add_route('/api/intervention/remark', InterventionRemarkApi())

    app.add_route('/analytics', AnalyticsPage())
    app.add_route('/api/report/export', ReportExportApi())

    app.add_route('/risk-warnings', RiskWarningsPage())
    app.add_route('/risk-users', RiskUsersPage())
    app.add_route('/api/risk/resolve', ResolveWarningApi())

    app.add_route('/notifications', NotificationsPage())
    app.add_route('/api/notifications', NotificationsApi())
    app.add_route('/api/notifications/read', MarkNotificationReadApi())
    app.add_route('/api/notifications/badge', NotificationsBadgePartial())

    app.add_route('/followup', FollowupPage())
    app.add_route('/anonymous/followup', FollowupSurveyPage())
    app.add_route('/api/followup/submit', FollowupSurveySubmitApi())
    app.add_route('/api/followup/{survey_id:int}', FollowupDetailApi())
    app.add_route('/api/followup/abnormal', FollowupMarkAbnormalApi())
    app.add_route('/api/followup/questions', FollowupQuestionsApi())
    app.add_route('/api/followup/questions/{question_id:int}', FollowupQuestionUpdateApi())
    app.add_route('/followup/analytics', FollowupAnalyticsPage())
    app.add_route('/api/followup/analytics/export', FollowupAnalyticsExportApi())

    return app

app = create_app()

if __name__ == '__main__':
    import sys
    host = '0.0.0.0'
    port = 8080
    if len(sys.argv) >= 2:
        port = int(sys.argv[1])
    print(f"Server starting on http://{host}:{port}")
    print(f"  Anonymous booking: http://{host}:{port}/anonymous/book")
    serve(app, host=host, port=port)
