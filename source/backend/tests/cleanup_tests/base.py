# booking cancellation, auto checkout, retention, maintenance and appointment tests
import datetime
import os
import sys
from unittest import mock

import support  # noqa: F401,E402

from support.sqlite_db import DbTestCase  # noqa: E402

H = datetime.timedelta(hours=1)
M = datetime.timedelta(minutes=1)
DAY = datetime.timedelta(days=1)


def now():
    return datetime.datetime.now().replace(microsecond=0)


def titles(case, uid):
    return [n["title"] for n in case.call("get", "/api/notifications", uid).get_json()["notifications"]]


class BookingCancelTestsBase(DbTestCase):
    def setUp(self):
        super().setUp()
        self.res = self.db.add_resource("Laser Cutter")

    def book(self, status="Approved", start=None, end=None, uid=None, **extra):
        start = start or now() + 2 * H
        return self.db.add_booking(self.res, uid or self.student, start, end or start + H, status=status, **extra)

    def cancel(self, bid, uid=None):
        return self.call("post", f"/api/bookings/{bid}/cancel", uid or self.student)


class AutoCheckoutTestsBase(DbTestCase):
    def setUp(self):
        super().setUp()
        from services.housekeeping import service as housekeeping
        self.hk = housekeeping
        self.res = self.db.add_resource("Oscilloscope", status="In Use")

    def booking(self, ended_minutes_ago, **extra):
        end = now() - ended_minutes_ago * M
        return self.db.add_booking(self.res, self.student, end - H, end, checked_in_at=end - H + 5 * M, **extra)

    def row(self, bid):
        return self.db.one("SELECT * FROM bookings WHERE id = %s", (bid,))

    def status(self):
        return self.db.one("SELECT status FROM resources WHERE id = %s", (self.res,))["status"]


if __name__ == "__main__":
    import unittest
    unittest.main()