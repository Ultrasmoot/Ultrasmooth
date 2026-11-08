# vs. a running session, Google unlink on e-mail change, cancelling an accepted appointment.
# Real models/controllers on a throw-away SQLite database (see sqlite_db.py).
import datetime
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlite_db import DbTestCase

H = datetime.timedelta(hours=1)
M = datetime.timedelta(minutes=1)
DAY = datetime.timedelta(days=1)


def now():
    return datetime.datetime.now().replace(microsecond=0)


def titles(case, uid):
    return [n["title"] for n in case.call("get", "/api/notifications", uid).get_json()["notifications"]]


class BookingCancelTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.res = self.db.add_resource("Laser Cutter")

    def book(self, status="Approved", start=None, end=None, uid=None, **extra):
        start = start or now() + 2 * H
        return self.db.add_booking(self.res, uid or self.student, start, end or start + H, status=status, **extra)

    def cancel(self, bid, uid=None):
        return self.call("post", f"/api/bookings/{bid}/cancel", uid or self.student)

    def test_cancel_pending_frees_the_slot_and_sets_cancelled_at(self):
        bid = self.book("Pending")
        r = self.cancel(bid)
        self.assertEqual(r.status_code, 200, r.get_json())
        b = r.get_json()["booking"]
        self.assertEqual(b["status"], "Cancelled")
        self.assertTrue(b["cancelled_at"])
        start = now() + 2 * H
        again = self.call("post", "/api/bookings", self.other,
                          {"resource_id": self.res, "start_time": start.isoformat(),
                           "end_time": (start + H).isoformat(), "purpose": "Taking the freed slot"})
        self.assertEqual(again.status_code, 201, again.get_json())

    def test_cancel_approved_tells_the_admins_but_pending_does_not(self):
        self.cancel(self.book("Pending"))
        self.assertNotIn("Booking cancelled", titles(self, self.admin))
        self.cancel(self.book("Approved", start=now() + 5 * H))
        self.assertIn("Booking cancelled", titles(self, self.admin))
        row = self.db.one("SELECT action FROM activity_log WHERE action = 'booking.cancelled'")
        self.assertIsNotNone(row)

    def test_only_the_owner_a_student_and_an_open_booking(self):
        bid = self.book("Approved")
        self.assertEqual(self.cancel(bid, self.other).status_code, 400) # someone else's = not found
        self.assertEqual(self.call("post", f"/api/bookings/{bid}/cancel").status_code, 401)
        self.assertEqual(self.cancel(bid, self.admin).status_code, 403)
        self.assertEqual(self.cancel(9999).status_code, 400)
        self.assertEqual(self.db.one("SELECT status FROM bookings WHERE id = %s", (bid,))["status"], "Approved")

    def test_refused_when_used_ended_or_already_decided(self):
        used = self.book("Approved", start=now() - 10 * M, end=now() + H, checked_in_at=now() - 5 * M)
        r = self.cancel(used)
        self.assertEqual(r.status_code, 400)
        self.assertIn("checked in", r.get_json()["error"])
        ended = self.book("Approved", start=now() - 3 * H, end=now() - H)
        self.assertIn("ended", self.cancel(ended).get_json()["error"])
        rejected = self.book("Rejected")
        self.assertEqual(self.cancel(rejected).status_code, 400)
        done = self.book("Pending")
        self.assertEqual(self.cancel(done).status_code, 200)
        self.assertEqual(self.cancel(done).status_code, 400) # twice

    def test_a_cancelled_booking_cannot_be_approved_or_checked_in(self):
        bid = self.book("Pending")
        self.cancel(bid)
        r = self.call("post", f"/api/bookings/{bid}/decide", self.admin, {"decision": "approve"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("cancelled", r.get_json()["error"])
        mine = self.call("get", "/api/bookings/mine", self.student).get_json()["bookings"]
        self.assertEqual(mine[0]["status"], "Cancelled")


class MaintenanceVsRunningSessionTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.res = self.db.add_resource("3D Printer", status="Maintenance")
        self.rec = self.db.execute(
            "INSERT INTO maintenance_records (resource_id, reported_by, description, status, issue_date) "
            "VALUES (%s, %s, 'Jammed', 'Open', %s)", (self.res, self.admin, datetime.date.today()))

    def status(self):
        return self.db.one("SELECT status FROM resources WHERE id = %s", (self.res,))["status"]

    def start_session(self):
        self.db.add_booking(self.res, self.student, now() - H, now() + H, checked_in_at=now() - 30 * M)

    def test_resolve_with_someone_checked_in_keeps_in_use(self):
        self.start_session()
        self.assertEqual(self.call("post", f"/api/maintenance/{self.rec}/resolve", self.admin).status_code, 200)
        self.assertEqual(self.status(), "In Use")

    def test_restore_with_someone_checked_in_keeps_in_use(self):
        self.start_session()
        r = self.call("post", f"/api/resources/{self.res}/restore", self.admin)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["resource"]["status"], "In Use")

    def test_without_a_session_it_is_available_as_before(self):
        self.assertEqual(self.call("post", f"/api/maintenance/{self.rec}/resolve", self.admin).status_code, 200)
        self.assertEqual(self.status(), "Available")
        self.db.execute("UPDATE resources SET status = 'Maintenance' WHERE id = %s", (self.res,))
        self.assertEqual(self.call("post", f"/api/resources/{self.res}/restore", self.admin).status_code, 200)
        self.assertEqual(self.status(), "Available")

    def test_a_finished_session_does_not_count(self):
        self.db.add_booking(self.res, self.student, now() - 3 * H, now() - 2 * H,
                            checked_in_at=now() - 3 * H, checked_out_at=now() - 2 * H)
        self.call("post", f"/api/maintenance/{self.rec}/resolve", self.admin)
        self.assertEqual(self.status(), "Available")


class AutoCheckoutTests(DbTestCase):
    def setUp(self):
        super().setUp()
        from services import housekeeping
        self.hk = housekeeping
        self.res = self.db.add_resource("Oscilloscope", status="In Use")

    def booking(self, ended_minutes_ago, **extra):
        end = now() - ended_minutes_ago * M
        return self.db.add_booking(self.res, self.student, end - H, end, checked_in_at=end - H + 5 * M, **extra)

    def row(self, bid):
        return self.db.one("SELECT * FROM bookings WHERE id = %s", (bid,))

    def status(self):
        return self.db.one("SELECT status FROM resources WHERE id = %s", (self.res,))["status"]

    def test_closed_after_the_20_minute_grace_and_resource_freed(self):
        bid = self.booking(25)
        self.assertEqual(self.hk.auto_checkout_overdue(grace_minutes=20), 1)
        self.assertIsNotNone(self.row(bid)["checked_out_at"])
        self.assertEqual(self.status(), "Available")
        self.assertIn("You were checked out automatically", titles(self, self.student))
        self.assertIsNotNone(self.db.one("SELECT id FROM activity_log WHERE action = 'checkout.auto'"))

    def test_inside_the_grace_period_nothing_happens(self):
        bid = self.booking(10)
        self.assertEqual(self.hk.auto_checkout_overdue(grace_minutes=20), 0)
        self.assertIsNone(self.row(bid)["checked_out_at"])
        self.assertEqual(self.status(), "In Use")

    def test_not_checked_in_or_already_checked_out_are_left_alone(self):
        end = now() - 2 * H
        self.db.add_booking(self.res, self.student, end - H, end)  # never checked in
        self.db.add_booking(self.res, self.other, end - H, end, checked_in_at=end - H,
                            checked_out_at=end - 10 * M)  # did check out
        self.assertEqual(self.hk.auto_checkout_overdue(grace_minutes=20), 0)

    def test_a_resource_in_maintenance_stays_blocked(self):
        self.db.execute("UPDATE resources SET status = 'Maintenance' WHERE id = %s", (self.res,))
        bid = self.booking(60)
        self.assertEqual(self.hk.auto_checkout_overdue(grace_minutes=20), 1)
        self.assertIsNotNone(self.row(bid)["checked_out_at"])
        self.assertEqual(self.status(), "Maintenance")

    def test_running_twice_does_not_repeat(self):
        self.booking(60)
        self.assertEqual(self.hk.auto_checkout_overdue(grace_minutes=20), 1)
        self.assertEqual(self.hk.auto_checkout_overdue(grace_minutes=20), 0)

    def test_the_resource_stays_in_use_if_another_session_is_running(self):
        self.booking(60)
        self.db.add_booking(self.res, self.other, now() - 30 * M, now() + H, checked_in_at=now() - 20 * M)
        self.hk.auto_checkout_overdue(grace_minutes=20)
        self.assertEqual(self.status(), "In Use")


class RetentionTests(DbTestCase):
    def setUp(self):
        super().setUp()
        from services import housekeeping
        self.hk = housekeeping

    def note(self, days_ago):
        self.db.execute("INSERT INTO notifications (user_id, kind, title, body, link_view, created_at) "
                        "VALUES (%s, 'x', 't', '', 'home', %s)", (self.student, now() - days_ago * DAY))

    def log(self, days_ago):
        self.db.execute("INSERT INTO activity_log (actor_name, action, summary, created_at) "
                        "VALUES ('System', 'booking.submitted', 's', %s)", (now() - days_ago * DAY,))

    def count(self, table):
        return self.db.one(f"SELECT COUNT(*) AS n FROM {table}")["n"]

    def test_old_rows_go_recent_rows_stay(self):
        for d in (1, 44, 46, 90):
            self.note(d)
            self.log(d)
        self.assertEqual(self.hk.purge_old_records(notification_days=45, activity_days=45), (2, 2))
        self.assertEqual((self.count("notifications"), self.count("activity_log")), (2, 2))

    def test_zero_days_keeps_everything(self):
        self.note(500)
        self.log(500)
        self.assertEqual(self.hk.purge_old_records(notification_days=0, activity_days=0), (0, 0))
        self.assertEqual((self.count("notifications"), self.count("activity_log")), (1, 1))

    def test_more_rows_than_one_batch(self):
        for _ in range(7):
            self.note(100)
        self.note(1)
        with mock.patch.object(self.hk, "DELETE_BATCH", 3):
            self.assertEqual(self.hk.purge_old_records(notification_days=45, activity_days=0), (7, 0))
        self.assertEqual(self.count("notifications"), 1)

    def test_run_once_does_both_jobs(self):
        self.note(100)
        res = self.db.add_resource("Printer", status="In Use")
        end = now() - H
        self.db.add_booking(res, self.student, end - H, end, checked_in_at=end - H)
        closed, deleted = self.hk.run_once(purge=True)
        self.assertEqual((closed, deleted[0]), (1, 1))


class GoogleUnlinkOnEmailChangeTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute("UPDATE users SET google_sub = 'g-123' WHERE id = %s", (self.student,))

    def sub(self):
        return self.db.one("SELECT google_sub FROM users WHERE id = %s", (self.student,))["google_sub"]

    def test_changing_the_email_removes_the_google_link(self):
        r = self.call("put", f"/api/admin/users/{self.student}", self.admin, {"email": "new.address@ku.th"})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertIsNone(self.sub())
        self.assertFalse(r.get_json()["user"]["google_linked"])
        log = self.db.one("SELECT summary FROM activity_log WHERE action = 'user.updated'")
        self.assertIn("Google link removed", log["summary"])

    def test_other_edits_keep_the_link(self):
        r = self.call("put", f"/api/admin/users/{self.student}", self.admin, {"full_name": "Renamed Student"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.sub(), "g-123")

    def test_same_email_sent_again_keeps_the_link(self):
        self.call("put", f"/api/admin/users/{self.student}", self.admin, {"email": "student@ku.th", "faculty": "Eng"})
        self.assertEqual(self.sub(), "g-123")


class CancelAcceptedAppointmentTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute("INSERT INTO professor_profiles (user_id, expertise, bio) VALUES (%s, 'Testing', 'x')",
                        (self.professor,))

    def appt(self, status="Accepted", start=None):
        start = start or now() + 2 * DAY
        return self.db.execute(
            "INSERT INTO appointments (student_id, professor_id, topic, start_time, end_time, status, created_at) "
            "VALUES (%s, %s, 'Thesis topic', %s, %s, %s, %s)",
            (self.student, self.professor, start, start + 30 * M, status, now()))

    def cancel(self, aid, uid=None):
        return self.call("post", f"/api/appointments/{aid}/cancel", uid or self.student)

    def test_accepted_future_appointment_can_be_cancelled_and_the_professor_is_told(self):
        aid = self.appt()
        r = self.cancel(aid)
        self.assertEqual((r.status_code, r.get_json()["appointment"]["status"]), (200, "Cancelled"))
        self.assertIn("Appointment cancelled", titles(self, self.professor))
        log = self.db.one("SELECT summary FROM activity_log WHERE action = 'appointment.cancelled'")
        self.assertIn("was accepted", log["summary"])

    def test_the_slot_is_free_for_the_professor_again(self):
        aid = self.appt(start=now() + 2 * DAY)
        self.cancel(aid)
        start = now() + 2 * DAY
        r = self.call("post", "/api/appointments", self.other,
                      {"professor_id": self.professor, "topic": "Another topic", "start_time": start.isoformat()})
        self.assertEqual(r.status_code, 201, r.get_json())
        new_id = r.get_json()["appointment"]["id"]
        self.assertEqual(self.call("post", f"/api/appointments/{new_id}/decide", self.professor,
                                   {"decision": "accept"}).status_code, 200)

    def test_accepted_that_has_started_cannot_be_cancelled(self):
        aid = self.appt(start=now() - 5 * M)
        r = self.cancel(aid)
        self.assertEqual(r.status_code, 400)
        self.assertIn("already started", r.get_json()["error"])

    def test_declined_or_cancelled_and_other_students_are_refused(self):
        self.assertEqual(self.cancel(self.appt("Declined")).status_code, 400)
        done = self.appt()
        self.assertEqual(self.cancel(done, self.other).status_code, 400)
        self.assertEqual(self.cancel(done).status_code, 200)
        self.assertEqual(self.cancel(done).status_code, 400)

    def test_pending_request_is_cancelled_as_before(self):
        r = self.cancel(self.appt("Pending"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("Appointment request cancelled", titles(self, self.professor))


if __name__ == "__main__":
    import unittest
    unittest.main()
