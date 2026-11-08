import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlite_db import DbTestCase  # noqa: E402

NOW = datetime.datetime.now
H = datetime.timedelta(hours=1)


def tomorrow(hour=10, hours=2):
    start = (NOW() + datetime.timedelta(days=1)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return start, start + hours * H


class ActivityLogTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.printer = self.db.add_resource("3D Printer")

    def actions(self, **params):
        query = "&".join(f"{k}={v}" for k, v in params.items())
        r = self.call("get", f"/api/activity?{query}", self.admin)
        self.assertEqual(r.status_code, 200, r.get_json())
        return [(i["action"], i["actor_name"]) for i in r.get_json()["items"]]

    def book(self):
        start, end = tomorrow()
        r = self.call("post", "/api/bookings", self.student,
                      {"resource_id": self.printer, "start_time": start.isoformat(), "end_time": end.isoformat(),
                       "purpose": "Print a part"})
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()["booking"]["id"]

    # Access control
    def test_only_admin_and_professor_can_read_the_log(self):
        self.assertEqual(self.call("get", "/api/activity").status_code, 401)
        for uid in (self.student, self.other):
            self.assertEqual(self.call("get", "/api/activity", uid).status_code, 403)
            self.assertEqual(self.call("get", "/api/activity/meta", uid).status_code, 403)
        for uid in (self.admin, self.professor):
            self.assertEqual(self.call("get", "/api/activity", uid).status_code, 200)

    # Log real booking actions
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
        r = self.call("post", f"/api/bookings/{bid}/decide", self.admin, {"decision": "reject"})  # Already decided
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

    # Filters (SRS-8)
    def test_filter_by_user_action_and_date(self):
        self.book()
        self.call("post", "/api/announcements", self.admin, {"title": "Hello", "body": "x"})
        self.assertEqual(self.actions(user=self.student), [("booking.submitted", "Demo Student")])
        self.assertEqual(self.actions(action="announcement.posted"), [("announcement.posted", "Demo Admin")])
        today = datetime.date.today().isoformat()
        self.assertEqual(len(self.actions(**{"from": today, "to": today})), 2)
        old = "2000-01-01"
        self.assertEqual(self.actions(**{"from": old, "to": old}), [])  # Empty results
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

    def test_meta_lists_actions_and_users_for_the_filters(self):
        self.book()
        meta = self.call("get", "/api/activity/meta", self.professor).get_json()
        self.assertIn({"value": "booking.submitted", "label": "Booking submitted"}, meta["actions"])
        self.assertEqual(meta["users"], [{"id": self.student, "name": "Demo Student"}])

    def test_the_log_is_append_only_through_the_api(self):
        for method in ("put", "delete", "patch"):
            self.assertIn(self.call(method, "/api/activity", self.admin).status_code, (404, 405))


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

    def test_login_required_and_each_user_sees_only_their_own(self):
        self.assertEqual(self.call("get", "/api/notifications").status_code, 401)
        self.assertEqual(self.call("get", "/api/notifications/unread-count").status_code, 401)
        self.book()
        self.assertEqual(self.inbox(self.admin)["unread"], 1)
        self.assertEqual(self.inbox(self.other)["unread"], 0)
        self.assertEqual(self.inbox(self.student)["notifications"], [])  # No self-notifications

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
        self.assertIn("A resource you booked is under maintenance", titles)  # Notify affected users
        self.assertEqual(self.inbox(self.professor)["notifications"], [])
        self.call("post", f"/api/maintenance/{rec}/resolve", self.admin)
        self.assertEqual(self.inbox(self.other)["notifications"][0]["title"], "Issue resolved")

    def test_announcement_reaches_everyone_except_the_author(self):
        self.call("post", "/api/announcements", self.admin, {"title": "Lab closed Friday", "body": "x"})
        for uid in (self.student, self.other, self.professor):
            self.assertEqual(self.inbox(uid)["notifications"][0]["body"], "Lab closed Friday")
        self.assertEqual(self.inbox(self.admin)["notifications"], [])

    def test_deactivated_users_get_no_notifications(self):
        self.db.execute("UPDATE users SET is_active = 0 WHERE id = %s", (self.other,))
        self.call("post", "/api/announcements", self.admin, {"title": "Hi", "body": "x"})
        self.assertEqual(self.db.one("SELECT COUNT(*) AS n FROM notifications WHERE user_id = %s", (self.other,))["n"], 0)

    def test_mark_one_and_mark_all_read_and_ownership(self):
        self.book(); self.book(self.other, hour=14)
        items = self.inbox(self.admin)["notifications"]
        self.assertEqual(self.inbox(self.admin)["unread"], 2)
        self.assertEqual(self.call("post", f"/api/notifications/{items[0]['id']}/read", self.student).status_code, 404)  # Not the owner
        self.assertEqual(self.inbox(self.admin)["unread"], 2)
        self.assertEqual(self.call("post", f"/api/notifications/{items[0]['id']}/read", self.admin).status_code, 200)
        self.assertEqual(self.call("get", "/api/notifications/unread-count", self.admin).get_json(), {"unread": 1})
        self.assertEqual(self.call("post", "/api/notifications/read-all", self.admin).status_code, 200)
        self.assertEqual(self.inbox(self.admin)["unread"], 0)

    def test_a_rolled_back_action_creates_no_notification(self):
        bid = self.book()
        self.call("post", f"/api/bookings/{bid}/decide", self.admin, {"decision": "approve"})
        before = self.inbox(self.student)["unread"]
        self.call("post", f"/api/bookings/{bid}/decide", self.admin, {"decision": "reject"})  # Already decided
        self.assertEqual(self.inbox(self.student)["unread"], before)


class DashboardTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.printer = self.db.add_resource("3D Printer", "Fabrication")
        self.cutter = self.db.add_resource("Laser Cutter", "Fabrication", status="In Use")
        self.scope = self.db.add_resource("Oscilloscope", "Electronics", status="Maintenance")
        self.db.add_resource("Old Scanner", "Electronics", archived=1)
        self.d = lambda days=30: self.call("get", f"/api/dashboard?days={days}", self.admin).get_json()

    def test_only_admin_and_professor(self):
        self.assertEqual(self.call("get", "/api/dashboard").status_code, 401)
        self.assertEqual(self.call("get", "/api/dashboard", self.student).status_code, 403)
        self.assertEqual(self.call("get", "/api/dashboard", self.professor).status_code, 200)

    def test_resource_counts_ignore_archived(self):
        r = self.d()["resources"]
        self.assertEqual(r, {"total": 3, "available": 1, "in_use": 1, "maintenance": 1})

    def test_active_bookings_means_approved_and_covering_now(self):
        now = NOW()
        self.db.add_booking(self.printer, self.student, now - H, now + H)  # Active now
        self.db.add_booking(self.printer, self.student, now + 5 * H, now + 6 * H)  # Future booking
        self.db.add_booking(self.cutter, self.other, now - H, now + H, checked_in_at=now - H, checked_out_at=now)  # Checked out
        self.db.add_booking(self.scope, self.other, now - H, now + H, status="Pending")  # Pending booking
        b = self.d()["bookings"]
        self.assertEqual((b["active"], b["pending"], b["in_use_now"]), (1, 1, 1))

    def test_open_issues_vs_waiting_for_review(self):
        today = datetime.date.today().isoformat()
        self.call("post", "/api/maintenance", self.admin, {"resource_id": self.printer, "description": "a", "date": today})
        self.call("post", "/api/maintenance", self.other, {"resource_id": self.cutter, "description": "b", "date": today})
        self.assertEqual(self.d()["issues"], {"open": 1, "pending_review": 1})

    def test_utilization_is_booked_hours_over_capacity_hours(self):
        now = NOW().replace(microsecond=0)
        start = now - datetime.timedelta(days=2)
        self.db.add_booking(self.printer, self.student, start, start + 12 * H)  # 12 booked hours
        self.db.add_booking(self.cutter, self.other, start, start + 24 * H, status="Rejected")  # Rejected booking
        self.db.add_booking(self.scope, self.other, start, start + 6 * H, status="Pending")  # Pending booking
        u = {x["category"]: x for x in self.d(days=10)["utilization"]}
        self.assertEqual((u["Fabrication"]["resources"], u["Fabrication"]["booked_hours"], u["Fabrication"]["utilization_pct"]), (2, 12.0, 2.5))
        self.assertEqual((u["Electronics"]["resources"], u["Electronics"]["utilization_pct"]), (1, 0.0))  # Archived resources excluded

    def test_booking_partly_outside_the_period_counts_only_the_overlap(self):
        now = NOW().replace(microsecond=0)
        self.db.add_booking(self.printer, self.student, now - datetime.timedelta(days=1, hours=3), now - datetime.timedelta(days=1) + 2 * H)
        # Last-day period
        fab = next(x for x in self.d(days=1)["utilization"] if x["category"] == "Fabrication")
        self.assertEqual(fab["booked_hours"], 2.0)

    def test_utilization_never_exceeds_100(self):
        now = NOW()
        self.db.add_booking(self.printer, self.student, now - datetime.timedelta(days=3), now + datetime.timedelta(days=3))
        self.db.add_booking(self.cutter, self.other, now - datetime.timedelta(days=3), now + datetime.timedelta(days=3))
        fab = next(x for x in self.d(days=1)["utilization"] if x["category"] == "Fabrication")
        self.assertEqual(fab["utilization_pct"], 100.0)

    def test_custom_period_and_validation(self):
        today = datetime.date.today()
        r = self.call("get", f"/api/dashboard?from={today}&to={today}", self.admin)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["period"]["hours"], 24.0)
        for q in ("days=0", "days=abc", "days=5000", "from=2026-01-01", "from=2026-02-01&to=2026-01-01",
                  "from=nope&to=nope", "from=2020-01-01&to=2026-01-01"):
            self.assertEqual(self.call("get", f"/api/dashboard?{q}", self.admin).status_code, 400, q)