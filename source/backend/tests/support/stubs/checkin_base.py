# base class for check in tests using the real app 
from support.stubs.maintenance_base import _token, silence_events
import unittest
from unittest import mock

import models.checkin.model as checkin_model
from app import create_app
from middleware.rate_limit import reset_rate_limits
from models.user.model import UserModel
from support.stubs.booking_sql import NOW, STUDENT, BookingsDB
from support.stubs.checkin_sql_write import ADMIN
from support.stubs.maintenance_base import DB


class CheckinBase(unittest.TestCase):
    def setUp(self):
        silence_events(self)
        reset_rate_limits()
        self.db = BookingsDB()
        self.clock = NOW
        self.sent = []  # to, resource name, code
        self.mail_fails = False
        for target in ("models.checkin.model.get_connection", "models.maintenance.model.get_connection",
                       "models.booking.model.get_connection", "models.resource.model.get_connection"):
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
        headers = {"Authorization": f"Bearer {_token(user)}"} if user else {}
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


class RequestCodeTestsBase(CheckinBase):
    pass


class VerifyTestsBase(CheckinBase):
    pass


class RejectReasonTestsBase(unittest.TestCase):
    def setUp(self):
        silence_events(self)
        reset_rate_limits()
        self.db = DB()
        p = mock.patch("models.booking.model.get_connection", side_effect=self.db.connection)
        p.start()
        self.addCleanup(p.stop)
        f = mock.patch.object(UserModel, "find_by_id", side_effect=lambda uid: self.db.users.get(int(uid)))
        f.start()
        self.addCleanup(f.stop)
        self.client = create_app().test_client()

    def decide(self, bid, decision, user=ADMIN, **extra):
        headers = {"Authorization": f"Bearer {_token(user)}"} if user else {}
        return self.client.post(f"/api/bookings/{bid}/decide", json={"decision": decision, **extra}, headers=headers)

    def reason_of(self, bid):
        return self.db.bookings[bid]["decision_reason"]