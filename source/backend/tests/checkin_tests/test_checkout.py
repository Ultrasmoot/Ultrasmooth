from support.stubs.checkin_base import CheckinBase
from support.stubs.booking_sql import ADMIN, MIN, OTHER, PRINTER
from support.stubs.booking_sql import PROFESSOR, STUDENT
# Part 7 of the tests in test_checkin.py 


class CheckoutTests(CheckinBase):
    def test_check_out_records_the_time_and_frees_the_resource(self):
        bid = self.db.add_booking()
        self.checkin(bid)
        self.clock += 45 * MIN
        r = self.checkout(bid)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["booking"]["checked_out_at"], self.clock.isoformat())
        self.assertEqual(self.db.status_of(PRINTER), "Available")

    def test_check_out_requires_a_check_in_and_cannot_be_repeated(self):
        bid = self.db.add_booking()
        self.assertIn("not checked in", self.checkout(bid).get_json()["error"])
        self.checkin(bid)
        self.assertEqual(self.checkout(bid).status_code, 200)
        self.assertIn("already checked out", self.checkout(bid).get_json()["error"])

    def test_late_check_out_after_the_booking_ended_still_works(self):
        bid = self.db.add_booking()
        self.checkin(bid)
        self.clock += 600 * MIN
        self.assertEqual(self.checkout(bid).status_code, 200)
        self.assertEqual(self.db.status_of(PRINTER), "Available")

    def test_check_out_never_lifts_a_maintenance_block(self):
        # An admin confirms a fault while the student is still using the resource.
        bid = self.db.add_booking()
        self.checkin(bid)
        r = self.call("post", "/api/maintenance", ADMIN, {"resource_id": PRINTER, "description": "Overheating",
                                                           "date": "2026-10-09"})
        self.assertEqual(r.status_code, 201, r.get_json())
        self.assertEqual(self.db.status_of(PRINTER), "Maintenance")
        self.clock += 30 * MIN
        r = self.checkout(bid)
        self.assertEqual(r.status_code, 200)
        self.assertIsNotNone(self.db.bookings[bid]["checked_out_at"])
        self.assertEqual(self.db.status_of(PRINTER), "Maintenance")

    def test_someone_else_cannot_check_out_for_you(self):
        bid = self.db.add_booking()
        self.checkin(bid)
        self.assertEqual(self.checkout(bid, OTHER).status_code, 400)
        self.assertEqual(self.db.status_of(PRINTER), "In Use")


class AccessTests(CheckinBase):
    def test_login_required(self):
        bid = self.db.add_booking()
        self.assertEqual(self.call("get", "/api/checkin/mine").status_code, 401)
        for path in ("code", "verify", "checkout"):
            self.assertEqual(self.call("post", f"/api/checkin/{bid}/{path}").status_code, 401, path)

    def test_only_students_may_use_it(self):
        bid = self.db.add_booking()
        for user in (ADMIN, PROFESSOR):
            self.assertEqual(self.call("get", "/api/checkin/mine", user).status_code, 403)
            for path in ("code", "verify", "checkout"):
                self.assertEqual(self.call("post", f"/api/checkin/{bid}/{path}", user).status_code, 403, (user, path))
        self.assertEqual(self.sent, [])

    def test_someone_elses_booking_looks_like_a_missing_one(self):
        bid = self.db.add_booking(uid=STUDENT)
        for path in ("code", "verify", "checkout"):
            r = self.call("post", f"/api/checkin/{bid}/{path}", OTHER, {"code": "123456"})
            self.assertEqual(r.status_code, 400, path)
            self.assertEqual(r.get_json()["error"], "Booking not found.")
        self.assertEqual(self.call("post", "/api/checkin/999/code", STUDENT).get_json()["error"], "Booking not found.")
        self.assertEqual(self.sent, [])
