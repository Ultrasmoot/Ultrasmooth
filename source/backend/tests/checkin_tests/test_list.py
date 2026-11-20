from support.stubs.checkin_base import CheckinBase
from support.stubs.booking_sql import MIN, NOW, OTHER, SCOPE, STUDENT
from support.stubs.checkin_base import VerifyTestsBase
from support.stubs.booking_sql import ADMIN, PRINTER
# Part 2 of the tests in test_checkin.py


class ListTests(CheckinBase):
    def test_bookings_are_split_into_in_use_ready_and_done(self):
        ready = self.db.add_booking(rid=SCOPE)
        using = self.db.add_booking()
        self.checkin(using)
        done = self.db.add_booking(start=NOW - 300 * MIN, end=NOW - 200 * MIN)
        self.db.bookings[done].update(checked_in_at=NOW - 290 * MIN, checked_out_at=NOW - 210 * MIN)
        data = self.call("get", "/api/checkin/mine", STUDENT).get_json()
        self.assertEqual([b["id"] for b in data["in_use"]], [using])
        self.assertEqual([b["id"] for b in data["ready"]], [ready])
        self.assertEqual([b["id"] for b in data["done"]], [done])
        self.assertTrue(data["ready"][0]["can_check_in"])

    def test_list_hides_other_peoples_pending_and_finished_unused_bookings(self):
        self.db.add_booking(uid=OTHER)
        self.db.add_booking(status="Pending")
        self.db.add_booking(start=NOW - 300 * MIN, end=NOW - 200 * MIN)  # ended, never used
        data = self.call("get", "/api/checkin/mine", STUDENT).get_json()
        self.assertEqual(data, {"in_use": [], "ready": [], "done": []})

    def test_blocked_bookings_carry_the_reason(self):
        self.db.resources[SCOPE]["status"] = "Maintenance"
        self.db.add_booking(rid=SCOPE)
        later = self.db.add_booking(start=NOW + 120 * MIN, end=NOW + 240 * MIN)
        ready = {b["id"]: b for b in self.call("get", "/api/checkin/mine", STUDENT).get_json()["ready"]}
        self.assertFalse(ready[1]["can_check_in"])
        self.assertIn("maintenance", ready[1]["block_reason"])
        self.assertEqual(ready[later]["block_reason"], "Check-in opens at 11:45.")


class VerifyTests_6(VerifyTestsBase):
    def test_resource_that_went_into_maintenance_while_the_email_was_on_its_way(self):
        bid = self.db.add_booking()
        code = self.code_for(bid)
        r = self.call("post", "/api/maintenance", ADMIN, {"resource_id": PRINTER, "description": "Jammed",
                                                           "date": "2026-10-09"})
        self.assertEqual(r.status_code, 201, r.get_json())
        r = self.verify(bid, code)
        self.assertEqual(r.status_code, 400)
        self.assertIn("under maintenance", r.get_json()["error"])
        self.assertEqual(self.db.status_of(PRINTER), "Maintenance")
        self.assertIsNone(self.db.bookings[bid]["checked_in_at"])

    def test_booking_that_ended_before_the_code_was_entered(self):
        bid = self.db.add_booking(end=NOW + 2 * MIN)
        code = self.code_for(bid)
        self.clock += 3 * MIN
        self.assertIn("has ended", self.verify(bid, code).get_json()["error"])
