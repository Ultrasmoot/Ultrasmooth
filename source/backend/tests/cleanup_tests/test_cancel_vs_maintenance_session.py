# booking cancellation and maintenance active 
from cleanup_tests.base import (
    BookingCancelTestsBase,
    DbTestCase,
    H,
    M,
    now,
)  # noqa: F401
import datetime


class BookingCancelTests_2(BookingCancelTestsBase):
    # cancelled booking 
    def test_a_cancelled_booking_cannot_be_approved_or_checked_in(self):
        bid = self.book("Pending")
        self.cancel(bid)
        r = self.call("post", f"/api/bookings/{bid}/decide", self.admin, {"decision": "approve"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("cancelled", r.get_json()["error"])
        mine = self.call("get", "/api/bookings/mine", self.student).get_json()["bookings"]
        self.assertEqual(mine[0]["status"], "Cancelled")


class MaintenanceVsRunningSessionTests(DbTestCase):
    # maintenance resolution active sessions
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