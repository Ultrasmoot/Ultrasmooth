# Part 4 of the tests in test_checkin.py
from support.stubs.checkin_base import RequestCodeTestsBase
from support.stubs.booking_sql import MIN, NOW, PRINTER, SCOPE, STUDENT
import datetime


class RequestCodeTests_4(RequestCodeTestsBase):
    def test_check_in_opens_exactly_15_minutes_before_start(self):
        ok = self.db.add_booking(start=NOW + 15 * MIN, end=NOW + 90 * MIN)
        self.assertEqual(self.call("post", f"/api/checkin/{ok}/code", STUDENT).status_code, 200)
        self.db.codes.clear()
        late = self.db.add_booking(rid=SCOPE, start=NOW + 16 * MIN, end=NOW + 90 * MIN)
        self.assertEqual(self.call("post", f"/api/checkin/{late}/code", STUDENT).status_code, 400)

    def test_already_checked_in(self):
        bid = self.db.add_booking()
        self.checkin(bid)
        self.clock += 60 * MIN
        r = self.call("post", f"/api/checkin/{bid}/code", STUDENT)
        self.assertIn("already checked in", r.get_json()["error"])

    def test_resend_cooldown_and_only_the_newest_code_works(self):
        bid = self.db.add_booking()
        first = self.code_for(bid)
        r = self.call("post", f"/api/checkin/{bid}/code", STUDENT)
        self.assertEqual(r.status_code, 429)
        self.assertTrue(1 <= r.get_json()["retry_after"] <= 30)
        self.assertEqual(len(self.sent), 1)
        self.clock += 31 * datetime.timedelta(seconds=1)
        second = self.code_for(bid)
        if first != second:
            r = self.verify(bid, first)
            self.assertEqual(r.status_code, 400)
        self.assertEqual(self.verify(bid, second).status_code, 200)

    def test_mail_failure_returns_502_keeps_no_code_and_does_not_start_the_cooldown(self):
        bid = self.db.add_booking()
        self.mail_fails = True
        r = self.call("post", f"/api/checkin/{bid}/code", STUDENT)
        self.assertEqual(r.status_code, 502)
        self.assertEqual(self.db.codes, {})
        self.assertEqual(self.db.status_of(PRINTER), "Available")
        self.mail_fails = False
        self.assertEqual(self.call("post", f"/api/checkin/{bid}/code", STUDENT).status_code, 200)
