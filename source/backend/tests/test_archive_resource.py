import datetime
import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("APP_ENV", "development")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_booking_reason as B  # noqa: E402
import test_maintenance as T  # noqa: E402
from app import create_app  # noqa: E402
from middleware.rate_limit import reset_rate_limits  # noqa: E402
from models.booking_model import BookingModel, ValidationError as BookingError  # noqa: E402
from models.user_model import UserModel  # noqa: E402

ADMIN, STUDENT, OTHER, PROFESSOR = T.ADMIN, T.STUDENT, T.OTHER_STUDENT, T.PROFESSOR
PRINTER, SCOPE = T.PRINTER, T.SCOPE
MIN = datetime.timedelta(minutes=1)


class Cur(B.Cur):
    statements = []  # Keep queries for checking row locks.

    def execute(self, sql, params=()):
        q, p = T._norm(sql), list(params or ())
        Cur.statements.append(q)
        if q.startswith("select count(*) from bookings where resource_id = %s and status in ('pending','approved')"):
            now = datetime.datetime.now()
            n = sum(1 for b in self.db.bookings.values()
                    if b["resource_id"] == p[0] and b["status"] in ("Pending", "Approved")
                    and b["end_time"] > now and not b["checked_out_at"])
            self._rows, self.rowcount = [(n,)], 0
        elif q.startswith("update resources set is_archived = 1 where id"):
            self.db.resources[p[0]]["is_archived"] = 1
            self._rows, self.rowcount = [], 1
        else:
            super().execute(sql, params)


class Conn(B.Conn):
    def cursor(self, dictionary=False):
        return Cur(self.db)


class DB(B.DB):
    def connection(self):
        return Conn(self)


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        reset_rate_limits()
        Cur.statements = []
        self.db = DB()
        self.now = datetime.datetime.now().replace(microsecond=0)
        for target in ("models.resource_model.get_connection", "models.booking_model.get_connection"):
            p = mock.patch(target, side_effect=self.db.connection)
            p.start()
            self.addCleanup(p.stop)
        f = mock.patch.object(UserModel, "find_by_id", side_effect=lambda uid: self.db.users.get(int(uid)))
        f.start()
        self.addCleanup(f.stop)
        self.client = create_app().test_client()

    # Test helpers
    def archive(self, rid=PRINTER, user=ADMIN):
        headers = {"Authorization": f"Bearer {T._token(user)}"} if user else {}
        return self.client.post(f"/api/resources/{rid}/archive", headers=headers)

    def add(self, status="Approved", start=-60, end=60, rid=PRINTER, uid=STUDENT):
        bid = self.db.add_booking(rid=rid, uid=uid, status=status,
                                  start=self.now + start * MIN, end=self.now + end * MIN)
        self.db.bookings[bid].update(decided_by=None, decided_at=None, decision_reason=None)
        return bid

    def is_archived(self, rid=PRINTER):
        return bool(self.db.resources[rid]["is_archived"])

    def assertRefused(self, fragment, **kw):
        r = self.archive(**kw)
        self.assertEqual(r.status_code, 400, r.get_json())
        self.assertIn(fragment, r.get_json()["error"])
        self.assertFalse(self.is_archived())  
        # Check that the resource stays unchanged.

    # Archiving allowed
    def test_resource_with_no_bookings_can_be_archived(self):
        r = self.archive()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"status": "archived"})
        self.assertTrue(self.is_archived())

    def test_row_is_locked_while_the_checks_run(self):
        self.archive()
        self.assertTrue(any(s.startswith("select status from resources where id = %s for update")
                            for s in Cur.statements))

    def test_bookings_that_are_over_or_not_live_do_not_block_archiving(self):
        self.add(status="Approved", start=-300, end=-200)            # Finished booking
        self.add(status="Pending", start=-300, end=-200)             # Expired pending request
        self.add(status="Rejected", start=60, end=120)               # Rejected request
        done = self.add(status="Approved", start=-30, end=240)       # Checked out early
        self.db.bookings[done].update(checked_in_at=self.now - 20 * MIN, checked_out_at=self.now - 5 * MIN)
        self.add(status="Approved", start=60, end=120, rid=SCOPE)    # Booking for another resource
        self.assertEqual(self.archive().status_code, 200)
        self.assertTrue(self.is_archived())

    def test_archiving_twice_is_harmless_and_unarchive_restores_it(self):
        self.assertEqual(self.archive().status_code, 200)
        self.assertEqual(self.archive().status_code, 200)
        r = self.client.post(f"/api/resources/{PRINTER}/unarchive",
                             headers={"Authorization": f"Bearer {T._token(ADMIN)}"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(self.is_archived())

    # Archiving refused
    def test_in_use_resource_cannot_be_archived(self):
        self.db.resources[PRINTER]["status"] = "In Use"
        self.assertRefused("currently In Use")

    def test_resource_with_someone_checked_in_cannot_be_archived(self):
        bid = self.add(status="Approved", start=-30, end=90)
        self.db.bookings[bid]["checked_in_at"] = self.now - 20 * MIN
        self.db.resources[PRINTER]["status"] = "In Use"
        self.assertRefused("currently In Use")

    def test_future_pending_booking_blocks_archiving(self):
        self.add(status="Pending", start=60, end=120)
        self.assertRefused("active bookings")

    def test_future_approved_booking_blocks_archiving(self):
        self.add(status="Approved", start=24 * 60, end=25 * 60)
        self.assertRefused("active bookings")

    def test_approved_booking_that_is_running_now_blocks_archiving(self):
        self.add(status="Approved", start=-30, end=30)  # Started, but not checked in or finished
        self.assertRefused("active bookings")

    def test_one_live_booking_among_finished_ones_still_blocks(self):
        self.add(status="Approved", start=-300, end=-200)
        self.add(status="Rejected", start=60, end=120)
        self.add(status="Pending", start=300, end=360)
        self.assertRefused("active bookings")

    def test_refused_resource_can_be_archived_after_the_booking_is_rejected(self):
        bid = self.add(status="Pending", start=60, end=120)
        self.assertEqual(self.archive().status_code, 400)
        self.db.bookings[bid]["status"] = "Rejected"
        self.assertEqual(self.archive().status_code, 200)

    def test_unknown_resource(self):
        r = self.archive(rid=999)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "Resource not found.")

    # Permissions and side effects
    def test_only_admins_can_archive(self):
        for user in (STUDENT, OTHER, PROFESSOR):
            self.assertEqual(self.archive(user=user).status_code, 403, user)
        self.assertEqual(self.archive(user=None).status_code, 401)
        self.assertFalse(self.is_archived())

    def test_archived_resource_is_hidden_from_non_admins_and_cannot_be_booked(self):
        self.archive()
        hdr = lambda u: {"Authorization": f"Bearer {T._token(u)}"}  # noqa: E731
        self.assertEqual(self.client.get(f"/api/resources/{PRINTER}", headers=hdr(STUDENT)).status_code, 404)
        self.assertEqual(self.client.get(f"/api/resources/{PRINTER}", headers=hdr(ADMIN)).status_code, 200)
        start = self.now + 600 * MIN
        with self.assertRaises(BookingError):
            BookingModel.create({"resource_id": PRINTER, "start_time": start.isoformat(),
                                 "end_time": (start + 60 * MIN).isoformat(), "purpose": "x"}, requester_id=STUDENT)