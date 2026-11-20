from support.stubs.checkin_base import RequestCodeTestsBase
from support.stubs.booking_sql import MIN, NOW, PRINTER, SCOPE, STUDENT
# Part 3 of the tests in test_checkin.py


class RequestCodeTests_3(RequestCodeTestsBase):
    def test_code_is_emailed_to_the_registered_address_and_stored_hashed(self):
        bid = self.db.add_booking()
        r = self.call("post", f"/api/checkin/{bid}/code", STUDENT)
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["email_hint"], "s*****@ku.th")
        self.assertEqual((body["expires_in"], body["resend_in"], body["max_attempts"]), (300, 30, 3))
        to, resource, code = self.sent[0]
        self.assertEqual((to, resource), ("s1@ku.th", "3D Printer"))
        self.assertRegex(code, r"^\d{6}$")
        stored = list(self.db.codes.values())[0]
        self.assertNotIn(code, str(stored))            # the code itself is never stored
        self.assertEqual(len(stored["code_hash"]), 64)
        self.assertEqual(stored["expires_at"], NOW + 5 * MIN)
        self.assertEqual(self.db.status_of(PRINTER), "Available")  # nothing changes yet

    def test_each_blocked_case_gets_its_own_error_and_sends_nothing(self):
        cases = []
        pending = self.db.add_booking(status="Pending"); cases.append((pending, "not approved"))
        early = self.db.add_booking(start=NOW + 16 * MIN, end=NOW + 90 * MIN); cases.append((early, "Check-in opens at 10:01."))
        tomorrow = self.db.add_booking(start=NOW + 1440 * MIN, end=NOW + 1500 * MIN); cases.append((tomorrow, "Check-in opens on 10 Oct at 09:45."))
        ended = self.db.add_booking(start=NOW - 120 * MIN, end=NOW - 1 * MIN); cases.append((ended, "has ended"))
        for bid, fragment in cases:
            r = self.call("post", f"/api/checkin/{bid}/code", STUDENT)
            self.assertEqual(r.status_code, 400, fragment)
            self.assertIn(fragment, r.get_json()["error"])
        self.db.resources[SCOPE]["status"] = "Maintenance"
        r = self.call("post", f"/api/checkin/{self.db.add_booking(rid=SCOPE)}/code", STUDENT)
        self.assertIn("under maintenance", r.get_json()["error"])
        self.db.resources[SCOPE]["status"] = "In Use"
        r = self.call("post", f"/api/checkin/{self.db.add_booking(rid=SCOPE)}/code", STUDENT)
        self.assertIn("in use by someone else", r.get_json()["error"])
        self.assertEqual((self.sent, self.db.codes), ([], {}))
