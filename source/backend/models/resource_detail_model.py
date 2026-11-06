# the page behind a resource card: schedule, and (for staff) who is using it,
# its repair history and its recent activity
import datetime

from database.db import get_connection
from models.activity_model import ActivityModel

SCHEDULE_LIMIT = 20
HISTORY_LIMIT = 10


def _now():
    return datetime.datetime.now()


class ResourceDetailModel:

    @classmethod
    def get(cls, resource_id: int, staff: bool, include_archived: bool = False, now=None):
        # Returns None when the resource does not exist (or is archived and the caller may not see it)
        now = now or _now()
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM resources WHERE id = %s", (resource_id,))
            resource = cur.fetchone()
            if not resource or (resource["is_archived"] and not include_archived):
                return None

            cur.execute(
                """SELECT b.id, b.start_time, b.end_time, b.purpose, u.full_name AS requester_name
                   FROM bookings b JOIN users u ON u.id = b.requester_id
                   WHERE b.resource_id = %s AND b.status = 'Approved' AND b.end_time > %s
                     AND b.checked_out_at IS NULL
                   ORDER BY b.start_time ASC LIMIT %s""",
                (resource_id, now, SCHEDULE_LIMIT),
            )
            bookings = cur.fetchall()

            result = {
                "resource": resource,
                "schedule": [
                    {"start_time": b["start_time"].isoformat(), "end_time": b["end_time"].isoformat(),
                     **({"requester_name": b["requester_name"], "purpose": b["purpose"]} if staff else {})}
                    for b in bookings
                ],
            }
            if not staff:
                return result   # students never get names, repair notes or the activity log

            cur.execute(
                """SELECT u.full_name AS requester_name, b.checked_in_at, b.end_time
                   FROM bookings b JOIN users u ON u.id = b.requester_id
                   WHERE b.resource_id = %s AND b.checked_in_at IS NOT NULL AND b.checked_out_at IS NULL
                   ORDER BY b.checked_in_at DESC LIMIT 1""",
                (resource_id,),
            )
            session = cur.fetchone()
            result["in_use_by"] = None if not session else {
                "name": session["requester_name"],
                "since": session["checked_in_at"].isoformat(),
                "booked_until": session["end_time"].isoformat(),
                "overdue": session["end_time"] < now,
            }

            cur.execute(
                """SELECT m.id, m.status, m.description, m.issue_date, m.closed_at, u.full_name AS reporter_name
                   FROM maintenance_records m JOIN users u ON u.id = m.reported_by
                   WHERE m.resource_id = %s ORDER BY m.created_at DESC, m.id DESC LIMIT %s""",
                (resource_id, HISTORY_LIMIT),
            )
            result["maintenance"] = [
                {"id": m["id"], "status": m["status"], "description": m["description"],
                 "issue_date": m["issue_date"].isoformat(), "reporter_name": m["reporter_name"],
                 "closed_at": m["closed_at"].isoformat() if m["closed_at"] else None}
                for m in cur.fetchall()
            ]
        finally:
            conn.close()

        from services.events import ACTIONS
        recent = ActivityModel.list(resource_id=resource_id, per_page=HISTORY_LIMIT)["items"]
        result["activity"] = [
            {"created_at": a["created_at"].isoformat(), "actor_name": a["actor_name"],
             "action_label": ACTIONS.get(a["action"], a["action"]), "summary": a["summary"]}
            for a in recent
        ]
        return result
