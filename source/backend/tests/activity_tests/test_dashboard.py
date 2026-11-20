# dashboard tests active bookings, issues and resource utilization
from activity_tests.base import (
    DashboardTestsBase,
    H,
    NOW,
)  # noqa: F401
import datetime


class DashboardTests_4(DashboardTestsBase):
    # active pending booking
    def test_active_bookings_means_approved_and_covering_now(self):
        now = NOW()
        self.db.add_booking(self.printer, self.student, now - H, now + H)  # active now
        self.db.add_booking(self.printer, self.student, now + 5 * H, now + 6 * H)  # future booking
        self.db.add_booking(self.cutter, self.other, now - H, now + H, checked_in_at=now - H, checked_out_at=now)  # checked out
        self.db.add_booking(self.scope, self.other, now - H, now + H, status="Pending")  # pending
        b = self.d()["bookings"]
        self.assertEqual((b["active"], b["pending"], b["in_use_now"]), (1, 1, 1))

    # open issues reviews
    def test_open_issues_vs_waiting_for_review(self):
        today = datetime.date.today().isoformat()
        self.call("post", "/api/maintenance", self.admin, {"resource_id": self.printer, "description": "a", "date": today})
        self.call("post", "/api/maintenance", self.other, {"resource_id": self.cutter, "description": "b", "date": today})
        self.assertEqual(self.d()["issues"], {"open": 1, "pending_review": 1})

    # utilization calculation
    def test_utilization_is_booked_hours_over_capacity_hours(self):
        now = NOW().replace(microsecond=0)
        start = now - datetime.timedelta(days=2)
        self.db.add_booking(self.printer, self.student, start, start + 12 * H)  # 12 booked hours
        self.db.add_booking(self.cutter, self.other, start, start + 24 * H, status="Rejected")  # excluded
        self.db.add_booking(self.scope, self.other, start, start + 6 * H, status="Pending")  # excluded
        u = {x["category"]: x for x in self.d(days=10)["utilization"]}
        # 2  x 240  = 480 capacity 12/480 = 2.5%
        self.assertEqual((u["Fabrication"]["resources"], u["Fabrication"]["booked_hours"], u["Fabrication"]["utilization_pct"]), (2, 12.0, 2.5))
        self.assertEqual((u["Electronics"]["resources"], u["Electronics"]["utilization_pct"]), (1, 0.0))  # archived resources excluded

    # overlap with the reporting period
    def test_booking_partly_outside_the_period_counts_only_the_overlap(self):
        now = NOW().replace(microsecond=0)
        self.db.add_booking(self.printer, self.student, now - datetime.timedelta(days=1, hours=3), now - datetime.timedelta(days=1) + 2 * H)
        # 2 overlapping hours count
        fab = next(x for x in self.d(days=1)["utilization"] if x["category"] == "Fabrication")
        self.assertEqual(fab["booked_hours"], 2.0)