import datetime
import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("APP_ENV", "development")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_booking_reason as B
import test_maintenance as T
from app import create_app
from middleware.rate_limit import reset_rate_limits
from models.booking_model import BookingModel, ValidationError
from models.checkin_model import EARLY_CHECKIN_MINUTES
from models.user_model import UserModel

ADMIN, STUDENT, OTHER, PRINTER, SCOPE, ARCHIVED = T.ADMIN, T.STUDENT, T.OTHER_STUDENT, T.PRINTER, T.SCOPE, T.ARCHIVED
MIN = datetime.timedelta(minutes=1)


class Cur(B.Cur):
    def execute(self, sql, params=()):
        q, p = T._norm(sql), list(params or ())
        if q.startswith("insert into bookings (resource_id, requester_id, start_time, end_time, purpose)"):
            db = self.db
            bid = db._bid
            db._bid += 1
            db.bookings[bid] = {"id": bid, "resource_id": p[0], "requester_id": p[1], "start_time": p[2],
                                "end_time": p[3], "purpose": p[4], "status": "Pending", "decided_by": None,
                                "decided_at": None, "decision_reason": None,
                                "checked_in_at": None, "checked_out_at": None}
            self._rows, self.rowcount, self.lastrowid = [], 0, bid
        else:
            super().execute(sql, params)


class Conn(B.Conn):
    def cursor(self, dictionary=False):
        return Cur(self.db)


class DB(B.DB):
    def connection(self):
        return Conn(self)


class InUseBase(unittest.TestCase):
    def setUp(self):
        reset_rate_limits()
        self.db = DB()
        self.base = datetime.datetime.now().replace(microsecond=0)
        for target, kw in (("models.booking_model.get_connection", {"side_effect": self.db.connection}),):
            p = mock.patch(target, **kw)
            p.start()
            self.addCleanup(p.stop)
        f = mock.patch.object(UserModel, "find_by_id", side_effect=lambda uid: self.db.users.get(int(uid)))
        f.start()
        self.addCleanup(f.stop)
        self.client = create_app().test_client()

    # helpers
    def in_use(self, rid=PRINTER):
        self.db.resources[rid]["status"] = "In Use"

    def occupy(self, ends_in_min, rid=PRINTER, uid=OTHER):
        """Someone has checked in to an Approved booking that ends `ends_in_min` minutes from now
        (negative = they have overstayed). The resource is therefore In Use."""
        bid = self.db.add_booking(rid=rid, uid=uid, status="Approved",
                                  start=self.base - 120 * MIN, end=self.base + ends_in_min * MIN)
        self.db.bookings[bid].update(checked_in_at=self.base - 100 * MIN, decided_by=None,
                                     decided_at=None, decision_reason=None)
        self.in_use(rid)
        return bid

    def book(self, start_in_min, hours=1, rid=PRINTER, uid=STUDENT):
        start = self.base + start_in_min * MIN
        return BookingModel.create(
            {"resource_id": rid, "start_time": start.isoformat(),
             "end_time": (start + datetime.timedelta(hours=hours)).isoformat(), "purpose": "Test"},
            requester_id=uid,
        )

    def assertRefused(self, fragment, *args, **kw):
        with self.assertRaises(ValidationError) as ctx:
            self.book(*args, **kw)
        self.assertIn(fragment, str(ctx.exception))


class CreateWhileInUseTests(InUseBase):
    def test_slot_that_starts_before_the_current_session_ends_is_refused(self):
        self.occupy(ends_in_min=120)
        self.assertRefused("in use until", 60)
        self.assertRefused("in use until", 5)
        self.assertEqual([b["requester_id"] for b in self.db.bookings.values()], [OTHER])  # nothing inserted

    def test_slot_starting_exactly_when_the_session_ends_or_later_is_allowed(self):
        self.occupy(ends_in_min=120)
        booking = self.book(120)
        self.assertEqual(booking["status"], "Pending")
        self.assertEqual(self.book(24 * 60 + 5, uid=OTHER)["status"], "Pending")

    def test_user_who_overstayed_does_not_block_later_slots(self):
        # booking ended 30 minutes ago but they have not checked out yet
        self.occupy(ends_in_min=-30)
        self.assertEqual(self.book(1)["status"], "Pending")
        self.assertEqual(self.book(300)["status"], "Pending")

    def test_status_set_by_hand_without_a_session_blocks_only_the_check_in_window(self):
        self.in_use()  # nobody is checked in
        self.assertRefused("currently marked In Use", 5)
        self.assertRefused("currently marked In Use", EARLY_CHECKIN_MINUTES - 1)
        self.assertEqual(self.book(EARLY_CHECKIN_MINUTES + 1)["status"], "Pending")
        self.assertEqual(self.book(2 * 24 * 60, uid=OTHER)["status"], "Pending")

    def test_session_on_another_resource_does_not_matter(self):
        self.occupy(ends_in_min=600, rid=SCOPE)
        self.assertEqual(self.book(10, rid=PRINTER)["status"], "Pending")  # printer is Available

    def test_a_session_that_has_been_checked_out_no_longer_counts(self):
        bid = self.occupy(ends_in_min=30)
        self.db.bookings[bid]["checked_out_at"] = self.base - 5 * MIN
        # Printer is still marked In Use here, but nobody is checked in
        self.assertRefused("currently marked In Use", 5)
        self.db.resources[PRINTER]["status"] = "Available"
        self.assertEqual(self.book(60)["status"], "Pending")

    def test_available_resource_is_not_affected_by_the_rule(self):
        self.assertEqual(self.book(1)["status"], "Pending")

    def test_maintenance_and_archived_are_still_refused(self):
        self.db.resources[PRINTER]["status"] = "Maintenance"
        self.assertRefused("Maintenance", 60)
        self.assertRefused("does not exist", 60, rid=ARCHIVED)
        self.assertRefused("does not exist", 60, rid=999)

    def test_overlap_with_another_approved_booking_is_still_refused_for_in_use_resources(self):
        self.occupy(ends_in_min=30)
        # Somebody else already holds an approved slot later today
        self.db.add_booking(rid=PRINTER, uid=OTHER, status="Approved",
                            start=self.base + 180 * MIN, end=self.base + 300 * MIN)
        self.assertRefused("already booked", 200)
        self.assertEqual(self.book(300)["status"], "Pending")

    def test_api_returns_400_with_the_reason(self):
        self.occupy(ends_in_min=120)
        start = self.base + 30 * MIN
        r = self.client.post(
            "/api/bookings",
            json={"resource_id": PRINTER, "start_time": start.isoformat(),
                  "end_time": (start + 60 * MIN).isoformat(), "purpose": "x"},
            headers={"Authorization": f"Bearer {T._token(STUDENT)}"},
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("in use until", r.get_json()["error"])


class ApproveWhileInUseTests(InUseBase):
    def decide(self, bid, decision="approve"):
        return self.client.post(f"/api/bookings/{bid}/decide", json={"decision": decision},
                                headers={"Authorization": f"Bearer {T._token(ADMIN)}"})

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


if __name__ == "__main__":
    unittest.main()
