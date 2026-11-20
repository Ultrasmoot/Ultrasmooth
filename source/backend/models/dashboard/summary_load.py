import models.dashboard.model as _m

class DashboardModelSummaryLoad:
    @classmethod
    def summary(cls, start, end, now=None):
        now = now or _m._now()
        resources, bookings, issues = cls._load(start, end, now)
        by_status, category_of, categories = cls._count_resources(resources)
        period_hours = (end - start).total_seconds() / 3600
        active, pending, booked_minutes = cls._tally_bookings(bookings, (start, end, now), category_of, categories)
        return {
            "period": {"from": start.isoformat(), "to": end.isoformat(), "hours": round(period_hours, 1)},
            "resources": {"total": len(resources), "available": by_status["Available"],
                          "in_use": by_status["In Use"], "maintenance": by_status["Maintenance"]},
            "bookings": {"active": active, "in_use_now": by_status["In Use"], "pending": pending},
            "issues": {"open": issues.get("Open", 0) + issues.get("In Progress", 0),
                       "pending_review": issues.get("Reported", 0)},
            "utilization": cls._utilization(categories, booked_minutes, period_hours),
        }

    @staticmethod
    def _load(start, end, now):
        conn = _m.get_connection()
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
        return resources, bookings, issues

    @staticmethod
    def _count_resources(resources):
        by_status = {"Available": 0, "In Use": 0, "Maintenance": 0}
        category_of = {}
        categories = {}
        for r in resources:
            by_status[r["status"]] = by_status.get(r["status"], 0) + 1
            category_of[r["id"]] = r["category"]
            categories[r["category"]] = categories.get(r["category"], 0) + 1
        return by_status, category_of, categories
