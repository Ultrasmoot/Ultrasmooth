import copy
import datetime
import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("APP_ENV", "development")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_maintenance as T  # (reuses its FakeDB / token helper)
from app import create_app 
from middleware.rate_limit import reset_rate_limits
from models import checkin_model 
from models.booking_model import BookingModel, ValidationError as BookingError
from models.user_model import UserModel

NOW = datetime.datetime(2026, 10, 9, 10, 0, 0)
MIN = datetime.timedelta(minutes=1)
STUDENT, OTHER, ADMIN, PROFESSOR = T.STUDENT, T.OTHER_STUDENT, T.ADMIN, T.PROFESSOR
PRINTER, SCOPE = T.PRINTER, T.SCOPE


class BookingsDB(T.FakeDB):
    def __init__(self):
        super().__init__()
        self.bookings, self.codes, self._bid, self._cid = {}, {}, 1, 1

    def add_booking(self, rid=PRINTER, uid=STUDENT, start=NOW - 30 * MIN, end=NOW + 90 * MIN, status="Approved"):
        bid = self._bid
        self._bid += 1
        self.bookings[bid] = {"id": bid, "resource_id": rid, "requester_id": uid, "start_time": start,
                              "end_time": end, "purpose": "Print a part", "status": status,
                              "checked_in_at": None, "checked_out_at": None}
        return bid

    def connection(self):
        return Conn(self)


class Conn(T.FakeConn):
    def __init__(self, db):
        super().__init__(db)
        self._snap2 = (copy.deepcopy(db.bookings), copy.deepcopy(db.codes))

    def cursor(self, dictionary=False):
        return Cur(self.db)

    def commit(self):
        super().commit()
        self._snap2 = (copy.deepcopy(self.db.bookings), copy.deepcopy(self.db.codes))

    def rollback(self):
        super().rollback()
        self.db.bookings, self.db.codes = copy.deepcopy(self._snap2[0]), copy.deepcopy(self._snap2[1])


class Cur(T.FakeCursor):
    def _joined(self, b):
        r = self.db.resources[b["resource_id"]]
        return {**b, "resource_name": r["name"], "resource_code": r["resource_code"], "resource_status": r["status"]}

    def execute(self, sql, params=()):
        db, q, p = self.db, T._norm(sql), list(params or ())
        if not q.startswith("insert"):
            self.lastrowid = 0  # only an INSERT sets lastrowid
        if q.startswith("select resource_id from bookings where id"):
            b = db.bookings.get(p[0])
            self._rows = [{"resource_id": b["resource_id"]}] if b else []
        elif q.startswith("select b.*, r.name as resource_name") and "where b.id = %s" in q:
            b = db.bookings.get(p[0])
            self._rows = [self._joined(b)] if b else []
        elif q.startswith("select b.*, r.name as resource_name") and "b.requester_id = %s and b.status = 'approved'" in q:
            uid, since = p
            rows = [b for b in db.bookings.values()
                    if b["requester_id"] == uid and b["status"] == "Approved" and b["end_time"] >= since]
            self._rows = [self._joined(b) for b in sorted(rows, key=lambda b: b["start_time"])]
        elif q.startswith("select created_at from checkin_codes where booking_id"):
            rows = [c for c in db.codes.values() if c["booking_id"] == p[0]]
            self._rows = [{"created_at": max(rows, key=lambda c: c["id"])["created_at"]}] if rows else []
        elif q.startswith("update checkin_codes set consumed_at = %s where booking_id"):
            for c in db.codes.values():
                if c["booking_id"] == p[1] and c["consumed_at"] is None:
                    c["consumed_at"] = p[0]
        elif q.startswith("insert into checkin_codes"):
            cid = db._cid
            db._cid += 1
            db.codes[cid] = {"id": cid, "booking_id": p[0], "user_id": p[1], "code_hash": p[2],
                             "expires_at": p[3], "attempts": 0, "consumed_at": None, "created_at": p[4]}
            self.lastrowid = cid
        elif q.startswith("delete from checkin_codes where id"):
            db.codes.pop(p[0], None)
        elif q.startswith("select * from checkin_codes where booking_id"):
            rows = [c for c in db.codes.values()
                    if c["booking_id"] == p[0] and c["user_id"] == p[1] and c["consumed_at"] is None]
            self._rows = [dict(max(rows, key=lambda c: c["id"]))] if rows else []
        elif q.startswith("update checkin_codes set attempts"):
            db.codes[p[1]]["attempts"] = p[0]
        elif q.startswith("update checkin_codes set consumed_at = %s where id"):
            db.codes[p[1]]["consumed_at"] = p[0]
        elif q.startswith("update bookings set checked_in_at"):
            db.bookings[p[1]]["checked_in_at"] = p[0]
        elif q.startswith("update bookings set checked_out_at"):
            db.bookings[p[1]]["checked_out_at"] = p[0]
        elif q.startswith("update resources set status = 'in use'"):
            db.resources[p[0]]["status"] = "In Use"
        elif q.startswith("select max(end_time) from bookings where resource_id = %s"):
            # BookingModel._active_session_end: the current user's booking (checked in, not out)
            ends = [b["end_time"] for b in db.bookings.values()
                    if b["resource_id"] == p[0] and b["status"] == "Approved"
                    and b["checked_in_at"] and not b["checked_out_at"]]
            self._rows = [(max(ends) if ends else None,)]
        else:
            self._rows, self.rowcount = [], 0
            return super().execute(sql, params)
        if not q.startswith(("select", "insert")):
            self._rows = []


class CheckinBase(unittest.TestCase):
    def setUp(self):
        reset_rate_limits()
        self.db = BookingsDB()
        self.clock = NOW
        self.sent = []  # (to, resource name, code)
        self.mail_fails = False
        for target in ("models.checkin_model.get_connection", "models.maintenance_model.get_connection",
                       "models.booking_model.get_connection", "models.resource_model.get_connection"):
            self._patch(mock.patch(target, side_effect=self.db.connection))
        self._patch(mock.patch.object(checkin_model, "_now", side_effect=lambda: self.clock))
        self._patch(mock.patch.object(UserModel, "find_by_id", side_effect=lambda uid: self.db.users.get(int(uid))))
        self._patch(mock.patch.object(checkin_model.mailer, "send_checkin_code", side_effect=self._send))
        self.client = create_app().test_client()

    def _patch(self, p):
        p.start()
        self.addCleanup(p.stop)

    def _send(self, to, resource, code, ttl):
        if self.mail_fails:
            raise OSError("smtp down")
        self.sent.append((to, resource, code))

    def call(self, method, path, user=None, json=None):
        headers = {"Authorization": f"Bearer {T._token(user)}"} if user else {}
        return getattr(self.client, method)(path, json=json, headers=headers)

    def code_for(self, bid, user=STUDENT):
        r = self.call("post", f"/api/checkin/{bid}/code", user)
        self.assertEqual(r.status_code, 200, r.get_json())
        return self.sent[-1][2]

    def verify(self, bid, code, user=STUDENT):
        return self.call("post", f"/api/checkin/{bid}/verify", user, {"code": code})

    def checkin(self, bid, user=STUDENT):
        r = self.verify(bid, self.code_for(bid, user), user)
        self.assertEqual(r.status_code, 200, r.get_json())
        return r

    def checkout(self, bid, user=STUDENT):
        return self.call("post", f"/api/checkin/{bid}/checkout", user)

    def wrong(self, code):
        return "000000" if code != "000000" else "111111"


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


class RequestCodeTests(CheckinBase):
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
        if first != second:  # (1-in-a-million chance the new random code equals the old one)
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


class VerifyTests(CheckinBase):
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
        self.assertEqual(list(self.db.codes.values())[0]["attempts"], 1)   # persisted, not rolled back
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
        self.clock += 31 * datetime.timedelta(seconds=1)   # a fresh code starts clean
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
        self.assertEqual(list(self.db.codes.values())[0]["attempts"], 0)  # format errors are not guesses
        other = self.db.add_booking(rid=SCOPE)
        self.assertIn("No active code", self.verify(other, "123456").get_json()["error"])

    def test_spaces_in_the_code_are_ignored(self):
        bid = self.db.add_booking()
        code = self.code_for(bid)
        self.assertEqual(self.verify(bid, f"{code[:3]} {code[3:]}").status_code, 200)

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

    def _book_next_day(self):
        # BookingModel.create checks "start time in the past" against the real clock,
        # so this booking must be built from the current time, not from the fixed NOW.
        real_now = datetime.datetime.now()
        return BookingModel.create({"resource_id": PRINTER, "start_time": (real_now + 1440 * MIN).isoformat(),
                                    "end_time": (real_now + 1500 * MIN).isoformat(), "purpose": "x"}, requester_id=OTHER)

    def test_resource_in_use_can_still_be_booked_for_a_later_slot(self):
        # "In Use" only means someone is using it right now. It must get past the
        # status gate and reach the time-overlap check, which is what prevents double booking.
        bid = self.db.add_booking()
        self.checkin(bid)
        self.assertEqual(self.db.status_of(PRINTER), "In Use")
        reached_conflict_check = RuntimeError("reached conflict check")
        with mock.patch.object(BookingModel, "_has_conflict", side_effect=reached_conflict_check):
            with self.assertRaises(RuntimeError):
                self._book_next_day()

    def test_resource_in_maintenance_cannot_be_booked(self):
        self.db.resources[PRINTER]["status"] = "Maintenance"
        with self.assertRaises(BookingError) as ctx:
            self._book_next_day()
        self.assertIn("Maintenance", str(ctx.exception))


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
        self.assertIsNotNone(self.db.bookings[bid]["checked_out_at"]) # the return is recorded but the resource stays blocked
        self.assertEqual(self.db.status_of(PRINTER), "Maintenance")        

    def test_someone_else_cannot_check_out_for_you(self):
        bid = self.db.add_booking()
        self.checkin(bid)
        self.assertEqual(self.checkout(bid, OTHER).status_code, 400)
        self.assertEqual(self.db.status_of(PRINTER), "In Use")


if __name__ == "__main__":
    unittest.main()