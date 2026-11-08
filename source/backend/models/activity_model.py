import datetime

from database.db import get_connection
from services.events import ACTIONS

DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100


class ValidationError(Exception):
    pass


def _parse_date(value, name):
    try:
        return datetime.date.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        raise ValidationError(f"{name} must be a date like 2026-10-31.")


def _positive_int(value, name, maximum=None):
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        raise ValidationError(f"{name} must be a number.")
    if number < 1 or (maximum and number > maximum):
        raise ValidationError(f"{name} must be between 1 and {maximum}." if maximum else f"{name} must be 1 or more.")
    return number


class ActivityModel:

    @classmethod
    def list(cls, date_from=None, date_to=None, user_id=None, action=None, resource_id=None,
             page=1, per_page=DEFAULT_PER_PAGE):
        """Newest first. Filters (all optional): date range (inclusive), the user who did it,
        the type of action, and the resource it concerns."""
        clauses, params = [], []
        if date_from:
            clauses.append("created_at >= %s")
            params.append(datetime.datetime.combine(_parse_date(date_from, "from"), datetime.time.min))
        if date_to:
            clauses.append("created_at < %s")
            params.append(datetime.datetime.combine(_parse_date(date_to, "to") + datetime.timedelta(days=1),
                                                    datetime.time.min))
        if date_from and date_to and _parse_date(date_from, "from") > _parse_date(date_to, "to"):
            raise ValidationError("'from' must not be after 'to'.")
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
        """People who appear in the log, for the 'user' filter."""
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
