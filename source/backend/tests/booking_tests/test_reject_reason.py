# Part 1 of the tests in test_booking_reason.py

from support.stubs.checkin_base import RejectReasonTestsBase
from support.stubs.checkin_sql_write import OTHER_STUDENT as OTHER, PROFESSOR, STUDENT
import datetime


class RejectReasonTests_1(RejectReasonTestsBase):
    def test_reject_with_a_reason_stores_it_and_returns_it(self):
        bid = self.db.pending()
        r = self.decide(bid, "reject", reason="  Printer is reserved for a class that day  ")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["booking"]["status"], "Rejected")
        self.assertEqual(r.get_json()["booking"]["decision_reason"], "Printer is reserved for a class that day")  # trimmed
        self.assertEqual(self.reason_of(bid), "Printer is reserved for a class that day")

    def test_the_reason_is_optional(self):
        for extra in ({}, {"reason": ""}, {"reason": "   "}, {"reason": None}):
            bid = self.db.pending()
            r = self.decide(bid, "reject", **extra)
            self.assertEqual(r.status_code, 200, extra)
            self.assertEqual(r.get_json()["booking"]["status"], "Rejected")
            self.assertIsNone(r.get_json()["booking"]["decision_reason"], extra)

    def test_reason_length_limit(self):
        bid = self.db.pending()
        r = self.decide(bid, "reject", reason="x" * 256)
        self.assertEqual(r.status_code, 400)
        self.assertIn("at most 255", r.get_json()["error"])
        self.assertEqual(self.db.bookings[bid]["status"], "Pending")   # nothing was decided
        self.assertEqual(self.decide(bid, "reject", reason="x" * 255).status_code, 200)

    def test_approving_ignores_any_reason(self):
        bid = self.db.pending()
        r = self.decide(bid, "approve", reason="should not be kept")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["booking"]["status"], "Approved")
        self.assertIsNone(self.reason_of(bid))

    def test_cannot_approve_a_started_booking(self):
        bid = self.db.pending(started=True)
        r = self.decide(bid, "approve")
        self.assertEqual(r.status_code, 400)
        self.assertIn("already started", r.get_json()["error"])
        self.assertEqual(self.db.bookings[bid]["status"], "Pending")
        # Rejecting a booking that has started is still allowed.
        self.assertEqual(self.decide(bid, "reject").status_code, 200)

    def test_cannot_approve_when_resource_is_in_maintenance(self):
        bid = self.db.pending()
        self.db.resources[self.db.bookings[bid]["resource_id"]]["status"] = "Maintenance"
        r = self.decide(bid, "approve")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Maintenance", r.get_json()["error"])
        self.assertEqual(self.db.bookings[bid]["status"], "Pending")
        self.assertEqual(self.decide(bid, "reject").status_code, 200)

    def test_cannot_approve_when_resource_is_archived(self):
        bid = self.db.pending()
        self.db.resources[self.db.bookings[bid]["resource_id"]]["is_archived"] = 1
        r = self.decide(bid, "approve")
        self.assertEqual(r.status_code, 400)
        self.assertIn("archived", r.get_json()["error"])
        self.assertEqual(self.db.bookings[bid]["status"], "Pending")
        self.assertEqual(self.decide(bid, "reject").status_code, 200)

    def test_cannot_approve_a_booking_that_overlaps_an_approved_one(self):
        # Re-checked at approval time even though create() normally prevents overlaps
        bid = self.db.pending()
        b = self.db.bookings[bid]
        clash = self.db.add_booking(rid=b["resource_id"], uid=OTHER, status="Approved",
                                    start=b["start_time"] + datetime.timedelta(minutes=30),
                                    end=b["end_time"] + datetime.timedelta(minutes=30))
        r = self.decide(bid, "approve")
        self.assertEqual(r.status_code, 400)
        self.assertIn("already booked", r.get_json()["error"])
        self.assertEqual(self.db.bookings[bid]["status"], "Pending")
        self.assertEqual(self.decide(bid, "reject").status_code, 200)
        self.assertEqual(self.db.bookings[clash]["status"], "Approved")
