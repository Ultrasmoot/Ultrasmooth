# reading the activity log (US-8, SRS-8). writing is done by services/events.py.
import datetime

from database.db import get_connection
from services.events.service import ACTIONS

DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100


class ValidationError(Exception):
    pass


class ActivityModel:

    @classmethod
    def list(cls, date_from=None, date_to=None, user_id=None, action=None, resource_id=None,
             page=1, per_page=DEFAULT_PER_PAGE):
        # newest first. Filters (all optional): date range (inclusive), the user who did it,
        # the type of action, and the resource it concerns.
        clauses, params = _date_range("created_at", date_from, date_to)
        if user_id not in (None, ""):
            clauses.append("actor_id = %s")
            params.append(_positive_int(user_id, "user"))
        if action:
            if not isinstance(action, str) or action not in ACTIONS:
                raise ValidationError("Unknown action type.")
            clauses.append("action = %s")
            params.append(action)
        if resource_id not in (None, ""):
            clauses.append("resource_id = %s")
            params.append(_positive_int(resource_id, "resource"))
        page = _positive_int(page, "page")
        per_page = _positive_int(per_page, "per_page", MAX_PER_PAGE)

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT COUNT(*) AS n FROM activity_log" + where, tuple(params))
            total = cur.fetchone()["n"]
            cur.execute(
                "SELECT * FROM activity_log" + where + " ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s",
                tuple(params) + (per_page, (page - 1) * per_page),
            )
            items = cur.fetchall()
        finally:
            conn.close()
        pages = max(1, -(-total // per_page))
        return {"items": items, "total": total, "page": page, "pages": pages, "per_page": per_page}

    @staticmethod
    def users():
        # people who appear in the log, for the 'user' filter
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """SELECT actor_id AS id, MAX(actor_name) AS name FROM activity_log
                   WHERE actor_id IS NOT NULL GROUP BY actor_id ORDER BY MAX(actor_name)"""
            )
            return cur.fetchall()
        finally:
            conn.close()


from models.activity.parse_date_positive_int import _date_range, _positive_int  # noqa: E402
