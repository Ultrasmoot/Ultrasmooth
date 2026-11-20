# base class for maintenance tests 
import datetime
import unittest
from unittest import mock

import jwt

from app import create_app
from config import Config
from middleware.rate_limit import reset_rate_limits
from models.user.model import UserModel
from support.stubs.checkin_sql_write import ADMIN, PRINTER, FakeDB
from support.stubs.booking_sql import BookingsDB, Conn, STUDENT
import support.stubs.booking_cursor as _c


def silence_events(testcase):
    """Disable event logging and notifications, which require real SQL.
    These are tested separately in the activity and resource tests."""
    import models.announcement.model as announcement_model
    import models.booking.model as booking_model
    import models.checkin.model as checkin_model
    import models.maintenance.model as maintenance_model
    import models.resource.model as resource_model
    for module in (announcement_model, booking_model, checkin_model, maintenance_model, resource_model):
        patcher = mock.patch.object(module, "events")
        patcher.start()
        testcase.addCleanup(patcher.stop)


def _token(user_id):
    # match _issue_token fake users have no password_hash
    from middleware.auth_middleware import password_fingerprint

    return jwt.encode(
        {"sub": str(user_id), "pwf": password_fingerprint(None)},
        Config.SECRET_KEY,
        algorithm="HS256",
    )


class MaintenanceTestBase(unittest.TestCase):
    def setUp(self):
        silence_events(self)
        reset_rate_limits()
        self.db = FakeDB()
        for target in ("models.maintenance.model.get_connection",
                       "models.booking.model.get_connection",
                       "models.resource.model.get_connection"):
            patcher = mock.patch(target, side_effect=self.db.connection)
            patcher.start()
            self.addCleanup(patcher.stop)
        finder = mock.patch.object(UserModel, "find_by_id",
                                   side_effect=lambda uid: self.db.users.get(int(uid)))
        finder.start()
        self.addCleanup(finder.stop)
        self.client = create_app().test_client()

    # helpers
    def call(self, method, path, user=None, json=None):
        headers = {"Authorization": f"Bearer {_token(user)}"} if user else {}
        return getattr(self.client, method)(path, json=json, headers=headers)

    def report(self, user, resource_id=PRINTER, description="Nozzle is jammed", **extra):
        body = {"resource_id": resource_id, "description": description,
                "date": datetime.date.today().isoformat(), **extra}
        return self.call("post", "/api/maintenance", user, body)

    def act(self, record_id, action, user=ADMIN, json=None):
        return self.call("post", f"/api/maintenance/{record_id}/{action}", user, json)


class ReportAndResolveFlowTestsBase(MaintenanceTestBase):
    pass


class Conn(Conn):
    def cursor(self, dictionary=False):
        return _c.Cur(self.db)


class DB(BookingsDB):
    def connection(self):
        return Conn(self)

    def pending(self, uid=STUDENT, started=False):
        # pending bookings start later approval is refused once started
        start = datetime.datetime.now() + datetime.timedelta(days=1)
        if started:
            start = datetime.datetime.now() - datetime.timedelta(hours=1)
        bid = self.add_booking(
            uid=uid, status="Pending", start=start, end=start + datetime.timedelta(hours=2)
        )
        self.bookings[bid].update(decided_by=None, decided_at=None, decision_reason=None)
        return bid