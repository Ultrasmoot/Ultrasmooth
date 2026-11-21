# booking cancellation, mail failure 
from cleanup_tests.base_jobs import (
    DbTestCase,
    H,
    StrictCursor,
    mock,
)  # noqa: F401
import datetime


class CancelTests(DbTestCase):
    # booking cancellation locked row 
    def setUp(self):
        super().setUp()
        now = datetime.datetime.now().replace(microsecond=0)
        self.rid = self.db.add_resource("Printer")
        self.bid = self.db.add_booking(self.rid, self.student, now + 2 * H, now + 3 * H, status="Pending")

    def strict(self):
        from database import db as real
        original = real.get_connection

        class Conn:
            def __init__(self, inner):
                self._inner = inner

            def cursor(self, *a, **kw):
                return StrictCursor(self._inner.cursor(*a, **kw))

            def __getattr__(self, name):
                return getattr(self._inner, name)

        return mock.patch("models.booking.model.get_connection", side_effect=lambda: Conn(original()))

    def test_cancel_reads_every_locked_row_before_the_next_statement(self):
        with self.strict():
            r = self.call("post", f"/api/bookings/{self.bid}/cancel", self.student)
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(self.db.one("SELECT status FROM bookings WHERE id = %s", (self.bid,))["status"], "Cancelled")

    def test_someone_elses_booking_looks_missing(self):
        r = self.call("post", f"/api/bookings/{self.bid}/cancel", self.other)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "Booking not found.")


class MailFailureTests(DbTestCase):
    # mail errors exposing details 
    def test_the_real_cause_is_logged_and_the_user_still_gets_502(self):
        from services.mailer import service as mailer
        now = datetime.datetime.now().replace(microsecond=0)
        rid = self.db.add_resource("Printer")
        bid = self.db.add_booking(rid, self.student, now - H / 2, now + H)
        with mock.patch.object(mailer, "send_checkin_code", side_effect=OSError("smtp refused")), \
                self.assertLogs("models.checkin.model", level="ERROR") as logs:
            r = self.call("post", f"/api/checkin/{bid}/code", self.student)
        self.assertEqual(r.status_code, 502)
        self.assertIn("smtp refused", "\n".join(logs.output))
        self.assertEqual(self.db.query("SELECT * FROM checkin_codes"), [])


class RemovedCodeTests(DbTestCase):
    # removed password reset 
    def test_unused_reset_lookup_is_gone(self):
        from models.user.model import UserModel
        self.assertFalse(hasattr(UserModel, "_find_valid_reset"))