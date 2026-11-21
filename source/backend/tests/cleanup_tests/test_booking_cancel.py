# booking cancellation tests
from cleanup_tests.base import (
    BookingCancelTestsBase,
    H,
    M,
    now,
    titles,
)  # noqa: F401


class BookingCancelTests_1(BookingCancelTestsBase):
    # approved booking cancellation
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
        self.assertEqual(self.cancel(bid, self.other).status_code, 400)         # other user's booking = not found
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
        self.assertEqual(self.cancel(done).status_code, 400)                    # cannot cancel twice