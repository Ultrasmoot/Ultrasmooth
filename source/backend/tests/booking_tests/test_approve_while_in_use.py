# Part 2 of the tests in test_booking_in_use.py
from support.stubs.in_use_base import ADMIN, CreateWhileInUseTestsBase, InUseBase, MIN, PRINTER, STUDENT
from support.stubs.maintenance_base import _token
import datetime


class CreateWhileInUseTests_2(CreateWhileInUseTestsBase):
    def test_api_returns_400_with_the_reason(self):
        self.occupy(ends_in_min=120)
        start = self.base + 30 * MIN
        r = self.client.post(
            "/api/bookings",
            json={"resource_id": PRINTER, "start_time": start.isoformat(),
                  "end_time": (start + 60 * MIN).isoformat(), "purpose": "x"},
            headers={"Authorization": f"Bearer {_token(STUDENT)}"},
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("in use until", r.get_json()["error"])


class ApproveWhileInUseTests(InUseBase):
    def decide(self, bid, decision="approve"):
        return self.client.post(f"/api/bookings/{bid}/decide", json={"decision": decision},
                                headers={"Authorization": f"Bearer {_token(ADMIN)}"})

    def pending_at(self, start_in_min, hours=2, rid=PRINTER):
        start = self.base + start_in_min * MIN
        bid = self.db.add_booking(rid=rid, uid=STUDENT, status="Pending", start=start,
                                  end=start + datetime.timedelta(hours=hours))
        self.db.bookings[bid].update(decided_by=None, decided_at=None, decision_reason=None)
        return bid

    def test_cannot_approve_a_slot_that_starts_before_the_current_session_ends(self):
        self.occupy(ends_in_min=240)
        bid = self.pending_at(60)
        r = self.decide(bid)
        self.assertEqual(r.status_code, 400)
        self.assertIn("in use until", r.get_json()["error"])
        self.assertEqual(self.db.bookings[bid]["status"], "Pending")
        self.assertEqual(self.decide(bid, "reject").status_code, 200)  # rejecting is always allowed

    def test_can_approve_a_slot_that_starts_after_the_current_session(self):
        self.occupy(ends_in_min=60)
        bid = self.pending_at(120)
        self.assertEqual(self.decide(bid).status_code, 200)
        self.assertEqual(self.db.bookings[bid]["status"], "Approved")

    def test_in_use_by_hand_blocks_approval_only_inside_the_check_in_window(self):
        self.in_use()
        soon = self.pending_at(5)
        later = self.pending_at(24 * 60)
        r = self.decide(soon)
        self.assertEqual(r.status_code, 400)
        self.assertIn("currently marked In Use", r.get_json()["error"])
        self.assertEqual(self.decide(later).status_code, 200)

    def test_approval_of_an_available_resource_is_unchanged(self):
        bid = self.pending_at(5)
        self.assertEqual(self.decide(bid).status_code, 200)
