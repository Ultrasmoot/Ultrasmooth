import datetime

from database.db import get_connection
from models.calendar.month_range_bounds import month_range, _bounds 

class ValidationError(Exception):
    pass


class CalendarModel:

    @staticmethod
    def resource_month(resource_id: int, month=None, staff=False, include_archived=False):
        """Returns None when the resource does not exist. Everyone gets the time slots;
        only staff (admin/professor) also get who booked and why."""
        first, nxt = month_range(month)
        lo, hi = _bounds(first, nxt)
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT id, name, resource_code, is_archived FROM resources WHERE id = %s", (resource_id,))
            resource = cur.fetchone()
            if not resource or (resource["is_archived"] and not include_archived):
                return None
            cur.execute(
                """SELECT b.id, b.start_time, b.end_time, b.status, b.purpose, u.full_name AS requester_name
                   FROM bookings b JOIN users u ON u.id = b.requester_id
                   WHERE b.resource_id = %s AND b.status IN ('Pending', 'Approved')
                     AND b.start_time < %s AND b.end_time > %s
                   ORDER BY b.start_time ASC, b.id ASC""",
                (resource_id, hi, lo),
            )
            rows = cur.fetchall()
        finally:
            conn.close()
        bookings = []
        for b in rows:
            item = {"id": b["id"], "start_time": b["start_time"].isoformat(),
                    "end_time": b["end_time"].isoformat(), "status": b["status"]}
            if staff:
                item["requester_name"] = b["requester_name"]
                item["purpose"] = b["purpose"]
            bookings.append(item)
        return {"resource": {"id": resource["id"], "name": resource["name"],
                             "resource_code": resource["resource_code"]},
                "month": first.strftime("%Y-%m"), "bookings": bookings}

    @staticmethod
    def professor_month(professor_id: int, month=None, now=None):
        """The professor's own appointments for the month: Accepted ones, and Pending ones
        that are still waiting (a Pending request whose time has passed is left out)."""
        first, nxt = month_range(month)
        lo, hi = _bounds(first, nxt)
        now = now or datetime.datetime.now()
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """SELECT a.id, a.topic, a.details, a.start_time, a.end_time, a.status, s.full_name AS student_name
                   FROM appointments a JOIN users s ON s.id = a.student_id
                   WHERE a.professor_id = %s AND a.status IN ('Pending', 'Accepted')
                     AND a.start_time >= %s AND a.start_time < %s
                   ORDER BY a.start_time ASC, a.id ASC""",
                (professor_id, lo, hi),
            )
            rows = cur.fetchall()
        finally:
            conn.close()
        return {
            "month": first.strftime("%Y-%m"),
            "appointments": [
                {"id": a["id"], "topic": a["topic"], "details": a["details"], "student_name": a["student_name"],
                 "start_time": a["start_time"].isoformat(), "end_time": a["end_time"].isoformat(),
                 "status": a["status"]}
                for a in rows if not (a["status"] == "Pending" and a["start_time"] <= now)
            ],
        }



