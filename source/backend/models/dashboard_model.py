import datetime

from database.db import get_connection

MAX_PERIOD_DAYS = 366
DEFAULT_DAYS = 30


class ValidationError(Exception):
    pass


def _now():
    return datetime.datetime.now()


def resolve_period(days=None, date_from=None, date_to=None, now=None):
    # selectable time period - returns (start, end) as datetimes with start < end
    now = now or _now()
    if date_from or date_to:
        if not (date_from and date_to):
            raise ValidationError("Give both 'from' and 'to' for a custom period.")
        try:
            start_day = datetime.date.fromisoformat(str(date_from).strip())
            end_day = datetime.date.fromisoformat(str(date_to).strip())
        except ValueError:
            raise ValidationError("'from' and 'to' must be dates like 2026-10-31.")
        if start_day > end_day:
            raise ValidationError("'from' must not be after 'to'.")
        start = datetime.datetime.combine(start_day, datetime.time.min)
        end = datetime.datetime.combine(end_day + datetime.timedelta(days=1), datetime.time.min)
    else:
        try:
            n = int(days if days not in (None, "") else DEFAULT_DAYS)
        except (TypeError, ValueError, OverflowError):
            raise ValidationError("days must be a number.")
        if n < 1:
            raise ValidationError("days must be 1 or more.")
        start, end = now - datetime.timedelta(days=n), now
    if (end - start).days > MAX_PERIOD_DAYS:
        raise ValidationError(f"The period can be at most {MAX_PERIOD_DAYS} days.")
    return start, end


class DashboardModel:

    @classmethod
    def summary(cls, start, end, now=None):
        now = now or _now()
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT id, category, status FROM resources WHERE is_archived = 0")
            resources = cur.fetchall()
            cur.execute(
                """SELECT b.resource_id, b.start_time, b.end_time, b.checked_out_at, b.status
                   FROM bookings b WHERE b.status IN ('Approved', 'Pending')
                     AND b.end_time > %s AND b.start_time < %s""",
                (min(start, now), max(end, now)),
            )
            bookings = cur.fetchall()
            cur.execute("SELECT status, COUNT(*) AS n FROM maintenance_records GROUP BY status")
            issues = {r["status"]: r["n"] for r in cur.fetchall()}
        finally:
            conn.close()

        by_status = {"Available": 0, "In Use": 0, "Maintenance": 0}
        category_of = {}
        categories = {}
        for r in resources:
            by_status[r["status"]] = by_status.get(r["status"], 0) + 1
            category_of[r["id"]] = r["category"]
            categories[r["category"]] = categories.get(r["category"], 0) + 1

        period_hours = (end - start).total_seconds() / 3600
        booked_minutes = {c: 0.0 for c in categories}
        active = pending = 0
        for b in bookings:
            if b["status"] == "Pending":
                pending += 1
                continue
            # "Active" is approved and covering this very moment (and not already handed back)
            if b["start_time"] <= now < b["end_time"] and b["checked_out_at"] is None:
                active += 1
            category = category_of.get(b["resource_id"])
            if category is None: # booking of an archived resource
                continue
            overlap = (min(b["end_time"], end) - max(b["start_time"], start)).total_seconds() / 60
            if overlap > 0:
                booked_minutes[category] += overlap

        utilization = []
        for category in sorted(categories):
            capacity_hours = categories[category] * period_hours
            booked_hours = booked_minutes[category] / 60
            pct = min(100.0, booked_hours / capacity_hours * 100) if capacity_hours > 0 else 0.0
            utilization.append({
                "category": category,
                "resources": categories[category],
                "booked_hours": round(booked_hours, 1),
                "utilization_pct": round(pct, 1),
            })

        return {
            "period": {"from": start.isoformat(), "to": end.isoformat(), "hours": round(period_hours, 1)},
            "resources": {"total": len(resources), "available": by_status["Available"],
                          "in_use": by_status["In Use"], "maintenance": by_status["Maintenance"]},
            "bookings": {"active": active, "in_use_now": by_status["In Use"], "pending": pending},
            "issues": {"open": issues.get("Open", 0) + issues.get("In Progress", 0),
                       "pending_review": issues.get("Reported", 0)},
            "utilization": utilization,
        }
