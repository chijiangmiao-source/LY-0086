import falcon
from datetime import datetime, date, timedelta
from app.templates import render_template
from app.database import get_conn, dict_rows, dict_row

class AnalyticsPage:
    def on_get(self, req, resp):
        user = req.context.user
        week_offset = int(req.get_param('week') or 0)
        today = date.today()
        monday = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
        week_dates = [(monday + timedelta(days=i)).isoformat() for i in range(7)]
        week_labels = ['周一','周二','周三','周四','周五','周六','周日']
        week_start = week_dates[0]
        week_end = week_dates[-1]

        conn = get_conn()
        c = conn.cursor()

        daily_stats = []
        placeholders7 = ','.join(['?'] * 7)
        c.execute(f"""SELECT appointment_date, 
                             COUNT(*) as total,
                             SUM(CASE WHEN checkin_status = 'checked_in' THEN 1 ELSE 0 END) as checked,
                             SUM(CASE WHEN no_show_marked = 1 THEN 1 ELSE 0 END) as noshow,
                             SUM(CASE WHEN checkin_status = 'cancelled' THEN 1 ELSE 0 END) as cancelled
                      FROM appointments 
                      WHERE appointment_date IN ({placeholders7})
                      GROUP BY appointment_date ORDER BY appointment_date""", week_dates)
        raw = {r['appointment_date']: dict(r) for r in c.fetchall()}
        grand_total = 0
        grand_checked = 0
        grand_noshow = 0
        for i, d in enumerate(week_dates):
            row = raw.get(d, {'appointment_date': d, 'total': 0, 'checked': 0, 'noshow': 0, 'cancelled': 0})
            if row['total'] > 0:
                row['noshow_rate'] = round(row['noshow'] / row['total'] * 100, 1)
                row['attend_rate'] = round(row['checked'] / row['total'] * 100, 1)
            else:
                row['noshow_rate'] = 0
                row['attend_rate'] = 0
            row['label'] = week_labels[i]
            row['short'] = d[5:]
            daily_stats.append(row)
            grand_total += row['total']
            grand_checked += row['checked']
            grand_noshow += row['noshow']

        overall_noshow_rate = round(grand_noshow / grand_total * 100, 1) if grand_total > 0 else 0
        overall_attend_rate = round(grand_checked / grand_total * 100, 1) if grand_total > 0 else 0

        c.execute("""SELECT cou.id, cou.name, cou.title,
                            COUNT(s.id) as scheduled_slots,
                            COUNT(DISTINCT a.id) as booked_appts
                     FROM counselors cou
                     LEFT JOIN schedules s ON cou.id = s.counselor_id 
                         AND s.schedule_date BETWEEN ? AND ?
                     LEFT JOIN appointments a ON s.id = a.schedule_id
                         AND a.checkin_status != 'cancelled'
                     WHERE cou.is_active = 1
                     GROUP BY cou.id ORDER BY booked_appts DESC""", (week_start, week_end))
        counselor_load = dict_rows(c.fetchall())
        for cl in counselor_load:
            cl['load_rate'] = round(cl['booked_appts'] / cl['scheduled_slots'] * 100, 1) if cl['scheduled_slots'] > 0 else 0
            if cl['load_rate'] >= 80:
                cl['load_level'] = 'high'
            elif cl['load_rate'] >= 50:
                cl['load_level'] = 'medium'
            else:
                cl['load_level'] = 'low'

        c.execute(f"""SELECT appointment_date, COUNT(DISTINCT anonymous_code) as unique_users
                      FROM appointments WHERE appointment_date IN ({placeholders7})
                      AND checkin_status != 'cancelled'
                      GROUP BY appointment_date ORDER BY appointment_date""", week_dates)
        unique_per_day = {r['appointment_date']: r['unique_users'] for r in c.fetchall()}
        for row in daily_stats:
            row['unique_users'] = unique_per_day.get(row['appointment_date'], 0)

        cooldown_history = []
        for i in range(6, -1, -1):
            d = (today - timedelta(days=i)).isoformat()
            c.execute("SELECT COUNT(*) as cnt FROM anonymous_users WHERE cooldown_until >= ? AND date(created_at) <= ?", (d, d))
            cnt1 = c.fetchone()['cnt']
            c.execute("SELECT COUNT(*) as cnt FROM anonymous_users WHERE cooldown_until = ?", (d,))
            cnt_new = c.fetchone()['cnt']
            c.execute("SELECT COUNT(*) as cnt FROM intervention_records WHERE action_type = 'lift_cooldown' AND date(created_at) = ?", (d,))
            cnt_lifted = c.fetchone()['cnt']
            cooldown_history.append({
                'date': d[5:],
                'active': cnt1,
                'new_cooldown': cnt_new,
                'lifted': cnt_lifted,
            })

        c.execute("""SELECT r.room_number, r.room_type,
                            COUNT(a.id) as usage_count
                     FROM rooms r
                     LEFT JOIN appointments a ON r.id = a.room_id
                         AND a.appointment_date BETWEEN ? AND ?
                         AND a.checkin_status != 'cancelled'
                     GROUP BY r.id ORDER BY usage_count DESC""", (week_start, week_end))
        room_usage = dict_rows(c.fetchall())

        c.execute("SELECT COUNT(*) FROM anonymous_users WHERE cooldown_until >= ?", (today.isoformat(),))
        current_cooldown = c.fetchone()['cnt']

        conn.close()

        max_total = max((s['total'] for s in daily_stats), default=1)
        max_cooldown = max((c['active'] for c in cooldown_history), default=1)
        for s in daily_stats:
            s['bar_pct'] = round(s['total'] / max_total * 100, 1) if max_total > 0 else 0
        for c in cooldown_history:
            c['bar_pct'] = round(c['active'] / max_cooldown * 100, 1) if max_cooldown > 0 else 0

        resp.content_type = 'text/html; charset=utf-8'
        resp.text = render_template('analytics.html', {
            'user': user,
            'week_start': week_start,
            'week_end': week_end,
            'week_offset': week_offset,
            'daily_stats': daily_stats,
            'grand_total': grand_total,
            'grand_checked': grand_checked,
            'grand_noshow': grand_noshow,
            'overall_noshow_rate': overall_noshow_rate,
            'overall_attend_rate': overall_attend_rate,
            'counselor_load': counselor_load,
            'cooldown_history': cooldown_history,
            'room_usage': room_usage,
            'current_cooldown': current_cooldown,
            'nav': 'analytics',
            'year': datetime.now().year,
        })
