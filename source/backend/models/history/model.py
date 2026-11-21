# check-in / check-out history for the admin.
# Nothing new is stored: every row comes from bookings.checked_in_at / checked_out_at
import datetime

from database.db import get_connection

DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100


class ValidationError(Exception):
    pass


class HistoryModel:

    @classmethod
    def list(cls, date_from=None, date_to=None, user_id=None, resource_id=None,
             page=1, per_page=DEFAULT_PER_PAGE):
        """Every booking someone has checked in to, newest check-in first.
        Filters (all optional): date range on the check-in time (inclusive), the user, the resource.
        A row without checked_out_at is still in use."""
        clauses, params = _date_range("b.checked_in_at", date_from, date_to)
        clauses.insert(0, "b.checked_in_at IS NOT NULL")
        if user_id not in (None, ""):
            clauses.append("b.requester_id = %s")
            params.append(_positive_int(user_id, "user"))
        if resource_id not in (None, ""):
            clauses.append("b.resource_id = %s")
            params.append(_positive_int(resource_id, "resource"))
        page = _positive_int(page, "page")
        per_page = _positive_int(per_page, "per_page", MAX_PER_PAGE)

        where = " WHERE " + " AND ".join(clauses)
        source = """ FROM bookings b JOIN resources r ON r.id = b.resource_id
                     JOIN users u ON u.id = b.requester_id"""
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT COUNT(*) AS n" + source + where, tuple(params))
            total = cur.fetchone()["n"]
            cur.execute(
                """SELECT b.id, b.resource_id, b.requester_id, b.start_time, b.end_time,
                          b.checked_in_at, b.checked_out_at, b.purpose,
                          r.name AS resource_name, r.resource_code, u.full_name AS user_name"""
                + source + where + " ORDER BY b.checked_in_at DESC, b.id DESC LIMIT %s OFFSET %s",
                tuple(params) + (per_page, (page - 1) * per_page),
            )
            items = cur.fetchall()
        finally:
            conn.close()
        pages = max(1, -(-total // per_page))
        return {"items": items, "total": total, "page": page, "pages": pages, "per_page": per_page}

    @staticmethod
    def options():
        """People and resources that appear in the history, for the two filter drop-downs."""
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """SELECT DISTINCT u.id, u.full_name AS name FROM bookings b
                   JOIN users u ON u.id = b.requester_id
                   WHERE b.checked_in_at IS NOT NULL ORDER BY u.full_name"""
            )
            users = cur.fetchall()
            cur.execute(
                """SELECT DISTINCT r.id, r.name FROM bookings b
                   JOIN resources r ON r.id = b.resource_id
                   WHERE b.checked_in_at IS NOT NULL ORDER BY r.name"""
            )
            resources = cur.fetchall()
        finally:
            conn.close()
        return {"users": users, "resources": resources}


from models.history.parse_date_positive_int import _date_range, _positive_int  # noqa: E402
