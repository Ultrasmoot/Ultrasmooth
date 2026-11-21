# notification and dashboard tests notifications, access and resource counts
from activity_tests.base import (
    DashboardTestsBase,
    DbTestCase,
    tomorrow,
)  # noqa: F401
import datetime


class NotificationTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.printer = self.db.add_resource("3D Printer")

    def inbox(self, uid):
        return self.call("get", "/api/notifications", uid).get_json()

    def book(self, uid=None, hour=10):
        start, end = tomorrow(hour)
        r = self.call("post", "/api/bookings", uid or self.student,
                      {"resource_id": self.printer, "start_time": start.isoformat(), "end_time": end.isoformat(),
                       "purpose": "Print"})
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()["booking"]["id"]

    # access control personal inbox
    def test_login_required_and_each_user_sees_only_their_own(self):
        self.assertEqual(self.call("get", "/api/notifications").status_code, 401)
        self.assertEqual(self.call("get", "/api/notifications/unread-count").status_code, 401)
        self.book()
        self.assertEqual(self.inbox(self.admin)["unread"], 1)
        self.assertEqual(self.inbox(self.other)["unread"], 0)
        self.assertEqual(self.inbox(self.student)["notifications"], [])  # not receive their notifications

    # booking notifications
    def test_new_booking_notifies_admins_and_the_decision_notifies_the_requester(self):
        bid = self.book()
        n = self.inbox(self.admin)["notifications"][0]
        self.assertEqual((n["title"], n["view"], n["is_read"]), ("New booking request", "bookings", False))
        self.assertIn("Demo Student", n["body"])
        self.call("post", f"/api/bookings/{bid}/decide", self.admin, {"decision": "reject", "reason": "Class that day"})
        mine = self.inbox(self.student)["notifications"][0]
        self.assertEqual((mine["title"], mine["view"]), ("Booking declined", "bookings"))
        self.assertIn("Class that day", mine["body"])
        self.call("post", f"/api/bookings/{self.book(hour=15)}/decide", self.admin, {"decision": "approve"})
        self.assertEqual(self.inbox(self.student)["notifications"][0]["title"], "Booking approved")

    # maintenance notifications
    def test_issue_flow_notifies_the_right_people(self):
        bid = self.book()
        self.call("post", f"/api/bookings/{bid}/decide", self.admin, {"decision": "approve"})
        r = self.call("post", "/api/maintenance", self.other, {"resource_id": self.printer, "description": "Jammed",
                      "date": datetime.date.today().isoformat()})
        rec = r.get_json()["record"]["id"]
        self.assertEqual(self.inbox(self.admin)["notifications"][0]["title"], "New issue report")
        self.call("post", f"/api/maintenance/{rec}/confirm", self.admin)
        self.assertEqual(self.inbox(self.other)["notifications"][0]["title"], "Issue confirmed")
        titles = [n["title"] for n in self.inbox(self.student)["notifications"]]
        self.assertIn("A resource you booked is under maintenance", titles)  
        self.assertEqual(self.inbox(self.professor)["notifications"], [])
        self.call("post", f"/api/maintenance/{rec}/resolve", self.admin)
        self.assertEqual(self.inbox(self.other)["notifications"][0]["title"], "Issue resolved")

    # announcement notifications
    def test_announcement_reaches_everyone_except_the_author(self):
        self.call("post", "/api/announcements", self.admin, {"title": "Lab closed Friday", "body": "x"})
        for uid in (self.student, self.other, self.professor):
            self.assertEqual(self.inbox(uid)["notifications"][0]["body"], "Lab closed Friday")
        self.assertEqual(self.inbox(self.admin)["notifications"], [])

    def test_deactivated_users_get_no_notifications(self):
        self.db.execute("UPDATE users SET is_active = 0 WHERE id = %s", (self.other,))
        self.call("post", "/api/announcements", self.admin, {"title": "Hi", "body": "x"})
        self.assertEqual(self.db.one("SELECT COUNT(*) AS n FROM notifications WHERE user_id = %s", (self.other,))["n"], 0)

    # read status ownership
    def test_mark_one_and_mark_all_read_and_ownership(self):
        self.book(); self.book(self.other, hour=14)
        items = self.inbox(self.admin)["notifications"]
        self.assertEqual(self.inbox(self.admin)["unread"], 2)
        self.assertEqual(self.call("post", f"/api/notifications/{items[0]['id']}/read", self.student).status_code, 404)  # Not owned
        self.assertEqual(self.inbox(self.admin)["unread"], 2)
        self.assertEqual(self.call("post", f"/api/notifications/{items[0]['id']}/read", self.admin).status_code, 200)
        self.assertEqual(self.call("get", "/api/notifications/unread-count", self.admin).get_json(), {"unread": 1})
        self.assertEqual(self.call("post", "/api/notifications/read-all", self.admin).status_code, 200)
        self.assertEqual(self.inbox(self.admin)["unread"], 0)

    # rollback behavior
    def test_a_rolled_back_action_creates_no_notification(self):
        bid = self.book()
        self.call("post", f"/api/bookings/{bid}/decide", self.admin, {"decision": "approve"})
        before = self.inbox(self.student)["unread"]
        self.call("post", f"/api/bookings/{bid}/decide", self.admin, {"decision": "reject"})  # Already decided
        self.assertEqual(self.inbox(self.student)["unread"], before)


class DashboardTests_3(DashboardTestsBase):
    # access control
    def test_only_admin_and_professor(self):
        self.assertEqual(self.call("get", "/api/dashboard").status_code, 401)
        self.assertEqual(self.call("get", "/api/dashboard", self.student).status_code, 403)
        self.assertEqual(self.call("get", "/api/dashboard", self.professor).status_code, 200)

    # resource counts
    def test_resource_counts_ignore_archived(self):
        r = self.d()["resources"]
        self.assertEqual(r, {"total": 3, "available": 1, "in_use": 1, "maintenance": 1})