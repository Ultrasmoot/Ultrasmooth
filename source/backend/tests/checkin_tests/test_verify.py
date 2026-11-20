# Part 5 of the tests in test_checkin.py
from support.stubs.checkin_base import VerifyTestsBase
from support.stubs.booking_sql import NOW, PRINTER, SCOPE
import datetime


class VerifyTests_5(VerifyTestsBase):
    def test_correct_code_checks_in_and_sets_resource_in_use(self):
        bid = self.db.add_booking()
        r = self.checkin(bid)
        booking = r.get_json()["booking"]
        self.assertEqual(booking["checked_in_at"], NOW.isoformat())
        self.assertEqual(booking["resource_status"], "In Use")
        self.assertEqual(self.db.status_of(PRINTER), "In Use")
        self.assertIsNotNone(list(self.db.codes.values())[0]["consumed_at"])

    def test_a_used_code_cannot_be_used_again(self):
        bid = self.db.add_booking()
        code = self.code_for(bid)
        self.assertEqual(self.verify(bid, code).status_code, 200)
        self.assertEqual(self.verify(bid, code).status_code, 400)

    def test_wrong_code_counts_down_and_the_counter_survives_the_failed_request(self):
        bid = self.db.add_booking()
        code = self.code_for(bid)
        r = self.verify(bid, self.wrong(code))
        self.assertEqual((r.status_code, r.get_json()["attempts_left"]), (400, 2))
        self.assertIn("2 attempts left", r.get_json()["error"])
        self.assertEqual(list(self.db.codes.values())[0]["attempts"], 1)
        r = self.verify(bid, self.wrong(code))
        self.assertEqual(r.get_json()["attempts_left"], 1)
        self.assertIn("1 attempt left", r.get_json()["error"])
        self.assertEqual(self.db.status_of(PRINTER), "Available")

    def test_three_wrong_guesses_lock_the_code_even_for_the_right_answer(self):
        bid = self.db.add_booking()
        code = self.code_for(bid)
        for _ in range(3):
            r = self.verify(bid, self.wrong(code))
        self.assertEqual(r.get_json()["attempts_left"], 0)
        r = self.verify(bid, code)
        self.assertEqual(r.status_code, 400)
        self.assertIn("Too many incorrect attempts", r.get_json()["error"])
        self.assertEqual(self.db.status_of(PRINTER), "Available")
        self.assertIsNone(self.db.bookings[bid]["checked_in_at"])
        self.clock += 31 * datetime.timedelta(seconds=1)
        self.assertEqual(self.verify(bid, self.code_for(bid)).status_code, 200)

    def test_expired_code(self):
        bid = self.db.add_booking()
        code = self.code_for(bid)
        self.clock += 301 * datetime.timedelta(seconds=1)
        r = self.verify(bid, code)
        self.assertEqual(r.status_code, 400)
        self.assertIn("expired", r.get_json()["error"])
        self.assertEqual(self.db.status_of(PRINTER), "Available")

    def test_malformed_and_missing_codes(self):
        bid = self.db.add_booking()
        self.code_for(bid)
        for bad in ("", "12345", "1234567", "12ab56", None):
            r = self.verify(bid, bad)
            self.assertEqual(r.status_code, 400, bad)
            self.assertIn("6-digit", r.get_json()["error"])
        self.assertEqual(list(self.db.codes.values())[0]["attempts"], 0)
        other = self.db.add_booking(rid=SCOPE)
        self.assertIn("No active code", self.verify(other, "123456").get_json()["error"])

    def test_spaces_in_the_code_are_ignored(self):
        bid = self.db.add_booking()
        code = self.code_for(bid)
        self.assertEqual(self.verify(bid, f"{code[:3]} {code[3:]}").status_code, 200)
