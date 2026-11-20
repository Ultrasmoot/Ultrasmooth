from support.stubs.maintenance_base import silence_events
from support.stubs.checkin_sql_write import ADMIN, ARCHIVED, OTHER_STUDENT, PRINTER, SCOPE, STUDENT
import datetime
import unittest
from unittest import mock

from app import create_app
from middleware.rate_limit import reset_rate_limits
from models.booking.model import BookingModel, ValidationError
from models.user.model import UserModel
from support.stubs.in_use_db import DB

ADMIN, STUDENT, OTHER, PRINTER, SCOPE, ARCHIVED = ADMIN, STUDENT, OTHER_STUDENT, PRINTER, SCOPE, ARCHIVED
MIN = datetime.timedelta(minutes=1)


class InUseBase(unittest.TestCase):
    def setUp(self):
        silence_events(self)
        reset_rate_limits()
        self.db = DB()
        self.base = datetime.datetime.now().replace(microsecond=0)
        for target, kw in (("models.booking.model.get_connection", {"side_effect": self.db.connection}),):
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


class CreateWhileInUseTestsBase(InUseBase):
    pass
