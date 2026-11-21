import datetime
import models.dashboard.model as _m

class DashboardModelTallyBookingsUtilization:
    @staticmethod
    def _tally_bookings(bookings, window, category_of, categories):
        start, end, now = window
        booked_minutes = {c: 0.0 for c in categories}
        active = pending = 0
        for b in bookings:
            if b["status"] == "Pending":
                pending += 1
                continue
            # "Active" = approved and covering this very moment (and not already handed back).
            if b["start_time"] <= now < b["end_time"] and b["checked_out_at"] is None:
                active += 1
            category = category_of.get(b["resource_id"])
            if category is None:           # booking of an archived resource: not counted
                continue
            overlap = (min(b["end_time"], end) - max(b["start_time"], start)).total_seconds() / 60
            if overlap > 0:
                booked_minutes[category] += overlap
        return active, pending, booked_minutes

    @staticmethod
    def _utilization(categories, booked_minutes, period_hours):
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
        return utilization

def _now():
    return datetime.datetime.now()
