# activity log tests access, event logging and filters
from activity_tests.base import (
    ActivityLogTestsBase,
)  # noqa: F401
import datetime


class ActivityLogTests_1(ActivityLogTestsBase):
    # access control
    def test_only_admin_and_professor_can_read_the_log(self):
        self.assertEqual(self.call("get", "/api/activity").status_code, 401)
        for uid in (self.student, self.other):
            self.assertEqual(self.call("get", "/api/activity", uid).status_code, 403)
            self.assertEqual(self.call("get", "/api/activity/meta", uid).status_code, 403)
        for uid in (self.admin, self.professor):
            self.assertEqual(self.call("get", "/api/activity", uid).status_code, 200)

    # event logging
    def test_booking_flow_is_logged_with_who_and_what(self):
        bid = self.book()
        r = self.call("post", f"/api/bookings/{bid}/decide", self.admin, {"decision": "reject", "reason": "Class that day"})
        self.assertEqual(r.status_code, 200)
        rows = self.call("get", "/api/activity", self.admin).get_json()["items"]
        self.assertEqual([(x["action"], x["actor_name"]) for x in rows],
                         [("booking.rejected", "Demo Admin"), ("booking.submitted", "Demo Student")])
        self.assertIn("Class that day", rows[0]["summary"])
        self.assertIn("3D Printer", rows[1]["summary"])
        self.assertEqual(rows[0]["action_label"], "Booking rejected")
        self.assertEqual(rows[0]["resource_id"], self.printer)

    def test_failed_decision_leaves_no_log_row(self):
        bid = self.book()
        self.call("post", f"/api/bookings/{bid}/decide", self.admin, {"decision": "approve"})
        before = len(self.actions())
        r = self.call("post", f"/api/bookings/{bid}/decide", self.admin, {"decision": "reject"})  # already decided
        self.assertEqual(r.status_code, 400)
        self.assertEqual(len(self.actions()), before)

    def test_failed_login_is_logged_without_the_password(self):
        r = self.client.post("/api/auth/login", json={"email": "admin@ku.th", "password": "wrong-password-123"})
        self.assertEqual(r.status_code, 401)
        items = self.call("get", "/api/activity?action=auth.login_failed", self.admin).get_json()["items"]
        self.assertEqual(len(items), 1)
        self.assertIn("admin@ku.th", items[0]["summary"])
        self.assertNotIn("wrong-password-123", str(items))
        self.assertIsNone(items[0]["actor_id"])

    def test_resource_changes_and_maintenance_are_logged(self):
        r = self.call("post", "/api/resources", self.admin, {"name": "Laser Cutter", "type": "Equipment",
                      "category": "Fabrication", "location": "Lab A", "owner": "Admin"})
        self.assertEqual(r.status_code, 201, r.get_json())
        rid = r.get_json()["resource"]["id"]
        self.call("put", f"/api/resources/{rid}", self.admin, {"location": "Lab B"})
        self.call("post", "/api/maintenance", self.admin, {"resource_id": rid, "description": "Cracked lens",
                  "date": datetime.date.today().isoformat()})
        got = [a for a, _ in self.actions()]
        for expected in ("resource.created", "resource.updated", "maintenance.reported"):
            self.assertIn(expected, got)

    def test_releasing_a_resource_and_editing_an_issue_are_logged(self):
        today = datetime.date.today().isoformat()
        rec = self.call("post", "/api/maintenance", self.admin, {"resource_id": self.printer, "description": "Jammed",
                        "date": today}).get_json()["record"]["id"]
        self.assertEqual(self.call("put", f"/api/maintenance/{rec}", self.admin, {"description": "Jammed badly"}).status_code, 200)
        r = self.call("post", f"/api/resources/{self.printer}/restore", self.admin)
        self.assertEqual(r.status_code, 200, r.get_json())
        got = [a for a, _ in self.actions()]
        self.assertIn("maintenance.updated", got)
        self.assertIn("maintenance.released", got)
        rows = self.call("get", "/api/activity?action=maintenance.released", self.admin).get_json()["items"]
        self.assertIn("1 open issue closed", rows[0]["summary"])

    def test_announcements_are_logged(self):
        r = self.call("post", "/api/announcements", self.admin, {"title": "Lab closed Friday", "body": "Power work"})
        self.assertEqual(r.status_code, 201, r.get_json())
        self.assertIn(("announcement.posted", "Demo Admin"), self.actions())

    # filters
    def test_filter_by_user_action_and_date(self):
        self.book()
        self.call("post", "/api/announcements", self.admin, {"title": "Hello", "body": "x"})
        self.assertEqual(self.actions(user=self.student), [("booking.submitted", "Demo Student")])
        self.assertEqual(self.actions(action="announcement.posted"), [("announcement.posted", "Demo Admin")])
        today = datetime.date.today().isoformat()
        self.assertEqual(len(self.actions(**{"from": today, "to": today})), 2)
        old = "2000-01-01"
        self.assertEqual(self.actions(**{"from": old, "to": old}), [])  # no records
        self.assertEqual(self.actions(resource=self.printer), [("booking.submitted", "Demo Student")])

    def test_dates_are_inclusive_of_the_whole_last_day(self):
        self.db.execute("INSERT INTO activity_log (actor_id, actor_name, action, summary, created_at) "
                        "VALUES (NULL, 'x', 'auth.login_failed', 'late', %s)", (datetime.datetime(2026, 5, 4, 23, 59, 59),))
        self.assertEqual(len(self.actions(**{"from": "2026-05-04", "to": "2026-05-04"})), 1)
        self.assertEqual(len(self.actions(**{"from": "2026-05-05", "to": "2026-05-05"})), 0)

    def test_bad_filters_are_400_not_500(self):
        for q in ("from=nope", "to=2026-13-40", "action=made.up", "user=abc", "page=0", "per_page=1000",
                  "from=2026-05-05&to=2026-05-01", "resource=-1"):
            self.assertEqual(self.call("get", f"/api/activity?{q}", self.admin).status_code, 400, q)