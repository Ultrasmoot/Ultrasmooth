# activity log tests pagination, filter metadata and append only behavior
# dashboard tests utilization limits, custom periods and validation
from activity_tests.base import (
    ActivityLogTestsBase,
    H,
)  # noqa: F401
import datetime
from activity_tests.base import (
    DashboardTestsBase,
    NOW,
)  # noqa: F401


class ActivityLogTests_2(ActivityLogTestsBase):
    # pagination
    def test_pagination_newest_first(self):
        for i in range(25):
            self.db.execute("INSERT INTO activity_log (actor_id, actor_name, action, summary, created_at) "
                            "VALUES (NULL, 'x', 'auth.login_failed', %s, %s)",
                            (f"n{i}", datetime.datetime(2026, 5, 1) + i * H))
        page1 = self.call("get", "/api/activity?per_page=10&page=1", self.admin).get_json()
        page3 = self.call("get", "/api/activity?per_page=10&page=3", self.admin).get_json()
        self.assertEqual((page1["total"], page1["pages"], len(page1["items"]), len(page3["items"])), (25, 3, 10, 5))
        self.assertEqual(page1["items"][0]["summary"], "n24")
        self.assertEqual(page3["items"][-1]["summary"], "n0")

    # filter metadata
    def test_meta_lists_actions_and_users_for_the_filters(self):
        self.book()
        meta = self.call("get", "/api/activity/meta", self.professor).get_json()
        self.assertIn({"value": "booking.submitted", "label": "Booking submitted"}, meta["actions"])
        self.assertEqual(meta["users"], [{"id": self.student, "name": "Demo Student"}])

    # API restrictions
    def test_the_log_is_append_only_through_the_api(self):
        for method in ("put", "delete", "patch"):
            self.assertIn(self.call(method, "/api/activity", self.admin).status_code, (404, 405))


class DashboardTests_5(DashboardTestsBase):
    # utilization limits
    def test_utilization_never_exceeds_100(self):
        now = NOW()
        self.db.add_booking(self.printer, self.student, now - datetime.timedelta(days=3), now + datetime.timedelta(days=3))
        self.db.add_booking(self.cutter, self.other, now - datetime.timedelta(days=3), now + datetime.timedelta(days=3))
        fab = next(x for x in self.d(days=1)["utilization"] if x["category"] == "Fabrication")
        self.assertEqual(fab["utilization_pct"], 100.0)

    # custom period validation
    def test_custom_period_and_validation(self):
        today = datetime.date.today()
        r = self.call("get", f"/api/dashboard?from={today}&to={today}", self.admin)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["period"]["hours"], 24.0)
        for q in ("days=0", "days=abc", "days=5000", "from=2026-01-01", "from=2026-02-01&to=2026-01-01",
                  "from=nope&to=nope", "from=2020-01-01&to=2026-01-01"):
            self.assertEqual(self.call("get", f"/api/dashboard?{q}", self.admin).status_code, 400, q)