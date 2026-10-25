import datetime
import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("APP_ENV", "development")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_checkin as C  
import test_maintenance as T 
from app import create_app 
from middleware.rate_limit import reset_rate_limits 
from models.user_model import UserModel 

ADMIN, STUDENT, OTHER, PROFESSOR = T.ADMIN, T.STUDENT, T.OTHER_STUDENT, T.PROFESSOR
NOW = datetime.datetime(2026, 10, 9, 10, 0, 0)


class Cur(C.Cur):
    def _named(self, b):
        r, u = self.db.resources[b["resource_id"]], self.db.users[b["requester_id"]]
        return {**b, "resource_name": r["name"], "requester_name": u["full_name"], "requester_email": u["email"]}

    def execute(self, sql, params=()):
        db, q, p = self.db, T._norm(sql), list(params or ())
        if q.startswith("select b.*, r.name as resource_name, u.full_name as requester_name"):
            rows = list(db.bookings.values())
            if "where b.id = %s" in q:
                rows = [b for b in rows if b["id"] == p[0]]
            elif "where b.requester_id = %s" in q:
                rows = [b for b in rows if b["requester_id"] == p[0]]
            elif "where b.status = 'pending'" in q:
                rows = [b for b in rows if b["status"] == "Pending"]
            self._rows = [self._named(b) for b in rows]
        elif q.startswith("select status from resources where id = %s"):
            self._rows = [(db.resources[p[0]]["status"],)]
        elif q.startswith("select * from bookings where id = %s for update"):
            b = db.bookings.get(p[0])
            self._rows = [dict(b)] if b else []
        elif q.startswith("select count(*) from bookings where resource_id = %s and status in"):
            marks = q.split("status in (")[1].split(")")[0].count("%s")
            rid, statuses, (end, start) = p[0], p[1:1 + marks], p[1 + marks:3 + marks]
            exclude = p[3 + marks] if "and id != %s" in q else None
            n = sum(1 for b in db.bookings.values()
                    if b["resource_id"] == rid and b["status"] in statuses
                    and b["start_time"] < end and b["end_time"] > start and b["id"] != exclude)
            self._rows = [(n,)]
        elif q.startswith("update bookings set status=%s, decided_by=%s, decided_at=now(), decision_reason=%s"):
            status, admin, reason, bid = p
            b = db.bookings[bid]
            self.rowcount = 0
            if b["status"] == "Pending":
                b.update(status=status, decided_by=admin, decided_at=NOW, decision_reason=reason)
                self.rowcount = 1
            self._rows = []
        else:
            super().execute(sql, params)


class Conn(C.Conn):
    def cursor(self, dictionary=False):
        return Cur(self.db)


class DB(C.BookingsDB):
    def connection(self):
        return Conn(self)

    def pending(self, uid=STUDENT, started=False):
        start = datetime.datetime.now() + datetime.timedelta(days=1)
        if started:
            start = datetime.datetime.now() - datetime.timedelta(hours=1)
        bid = self.add_booking(
            uid=uid, status="Pending", start=start, end=start + datetime.timedelta(hours=2)
        )
        self.bookings[bid].update(decided_by=None, decided_at=None, decision_reason=None)
        return bid


class RejectReasonTests(unittest.TestCase):
    def setUp(self):
        reset_rate_limits()
        self.db = DB()
        for target in ("models.booking_model.get_connection",):
            p = mock.patch(target, side_effect=self.db.connection)
            p.start()
            self.addCleanup(p.stop)
        f = mock.patch.object(UserModel, "find_by_id", side_effect=lambda uid: self.db.users.get(int(uid)))
        f.start()
        self.addCleanup(f.stop)
        self.client = create_app().test_client()

    def decide(self, bid, decision, user=ADMIN, **extra):
        headers = {"Authorization": f"Bearer {T._token(user)}"} if user else {}
        return self.client.post(f"/api/bookings/{bid}/decide", json={"decision": decision, **extra}, headers=headers)

    def reason_of(self, bid):
        return self.db.bookings[bid]["decision_reason"]

    def test_reject_with_a_reason_stores_it_and_returns_it(self):
        bid = self.db.pending()
        r = self.decide(bid, "reject", reason="  Printer is reserved for a class that day  ")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["booking"]["status"], "Rejected")
        self.assertEqual(r.get_json()["booking"]["decision_reason"], "Printer is reserved for a class that day")
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
        # Rejecting a booking that has started is still allowed
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

    def test_back_to_back_and_other_resource_bookings_do_not_block_approval(self):
        bid = self.db.pending()
        b = self.db.bookings[bid]
        # ends exactly when this one starts == no overlap
        self.db.add_booking(rid=b["resource_id"], uid=OTHER, status="Approved",
                            start=b["start_time"] - datetime.timedelta(hours=2), end=b["start_time"])
        # same time, different resource
        self.db.add_booking(rid=T.SCOPE, uid=OTHER, status="Approved", start=b["start_time"], end=b["end_time"])
        self.assertEqual(self.decide(bid, "approve").status_code, 200)

    def test_wrong_json_types_are_a_400_not_a_500(self):
        bid = self.db.pending()
        for decision in (["approve"], {"a": 1}, 5, None, True):
            self.assertEqual(self.decide(bid, decision).status_code, 400, decision)
        self.assertEqual(self.decide(bid, "reject", reason=["x"]).status_code, 400)
        self.assertEqual(self.decide(bid, "reject", reason=123).status_code, 400)
        self.assertEqual(self.db.bookings[bid]["status"], "Pending")

    def test_only_admins_can_decide(self):
        bid = self.db.pending()
        for user in (STUDENT, OTHER, PROFESSOR):
            self.assertEqual(self.decide(bid, "reject", user=user, reason="no").status_code, 403, user)
        self.assertEqual(self.decide(bid, "reject", user=None, reason="no").status_code, 401)
        self.assertEqual(self.db.bookings[bid]["status"], "Pending")

    def test_a_second_decision_cannot_overwrite_the_first_reason(self):
        bid = self.db.pending()
        self.decide(bid, "reject", reason="First reason")
        r = self.decide(bid, "reject", reason="Second reason")
        self.assertEqual(r.status_code, 400)
        self.assertIn("already rejected", r.get_json()["error"])
        self.assertEqual(self.reason_of(bid), "First reason")

    def test_the_requester_sees_the_reason_but_other_students_do_not_see_the_booking(self):
        bid = self.db.pending(uid=STUDENT)
        self.decide(bid, "reject", reason="Resource is being serviced")
        token = {"Authorization": f"Bearer {T._token(STUDENT)}"}
        mine = self.client.get("/api/bookings/mine", headers=token).get_json()["bookings"]
        self.assertEqual([(b["status"], b["decision_reason"]) for b in mine], [("Rejected", "Resource is being serviced")])
        other = self.client.get("/api/bookings/mine", headers={"Authorization": f"Bearer {T._token(OTHER)}"})
        self.assertEqual(other.get_json()["bookings"], [])


if __name__ == "__main__":
    unittest.main()
