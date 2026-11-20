from support.stubs.maintenance_base import _token, silence_events
from support.stubs.checkin_sql_write import ADMIN, OTHER_STUDENT, PRINTER, PROFESSOR, SCOPE, STUDENT
import datetime
import unittest
from unittest import mock

from app import create_app
from middleware.rate_limit import reset_rate_limits
from models.user.model import UserModel
from support.stubs.archive_db import DB, Cur

ADMIN, STUDENT, OTHER, PROFESSOR = ADMIN, STUDENT, OTHER_STUDENT, PROFESSOR
MIN = datetime.timedelta(minutes=1)


class ArchiveTestsBase(unittest.TestCase):
    def setUp(self):
        silence_events(self)
        reset_rate_limits()
        Cur.statements = []
        self.db = DB()
        self.now = datetime.datetime.now().replace(microsecond=0)
        for target in ("models.resource.model.get_connection", "models.booking.model.get_connection"):
            p = mock.patch(target, side_effect=self.db.connection)
            p.start()
            self.addCleanup(p.stop)
        f = mock.patch.object(UserModel, "find_by_id", side_effect=lambda uid: self.db.users.get(int(uid)))
        f.start()
        self.addCleanup(f.stop)
        self.client = create_app().test_client()

    # helpers
    def archive(self, rid=PRINTER, user=ADMIN):
        headers = {"Authorization": f"Bearer {_token(user)}"} if user else {}
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
        self.assertFalse(self.is_archived())  # nothing change
