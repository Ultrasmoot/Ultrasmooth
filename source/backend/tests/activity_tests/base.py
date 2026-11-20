# activity log, notifications and dashboard 
import datetime
import os
import sys

import support  # noqa: F401,E402

from support.sqlite_db import DbTestCase  # noqa: E402

NOW = datetime.datetime.now
H = datetime.timedelta(hours=1)


def tomorrow(hour=10, hours=2):
    start = (NOW() + datetime.timedelta(days=1)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return start, start + hours * H


class ActivityLogTestsBase(DbTestCase):
    def setUp(self):
        super().setUp()
        self.printer = self.db.add_resource("3D Printer")

    def actions(self, **params):
        query = "&".join(f"{k}={v}" for k, v in params.items())
        r = self.call("get", f"/api/activity?{query}", self.admin)
        self.assertEqual(r.status_code, 200, r.get_json())
        return [(i["action"], i["actor_name"]) for i in r.get_json()["items"]]

    def book(self):
        start, end = tomorrow()
        r = self.call("post", "/api/bookings", self.student,
                      {"resource_id": self.printer, "start_time": start.isoformat(), "end_time": end.isoformat(),
                       "purpose": "Print a part"})
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()["booking"]["id"]


class DashboardTestsBase(DbTestCase):
    def setUp(self):
        super().setUp()
        self.printer = self.db.add_resource("3D Printer", "Fabrication")
        self.cutter = self.db.add_resource("Laser Cutter", "Fabrication", status="In Use")
        self.scope = self.db.add_resource("Oscilloscope", "Electronics", status="Maintenance")
        self.db.add_resource("Old Scanner", "Electronics", archived=1)
        self.d = lambda days=30: self.call("get", f"/api/dashboard?days={days}", self.admin).get_json()