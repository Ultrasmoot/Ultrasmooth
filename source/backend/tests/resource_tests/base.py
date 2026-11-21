import datetime
import os
import sys

import support 

from support.sqlite_db import DbTestCase  

H = datetime.timedelta(hours=1)
DAY = datetime.timedelta(days=1)


def at(days=1, hour=10, minute=0):
    return (datetime.datetime.now() + days * DAY).replace(hour=hour, minute=minute, second=0, microsecond=0)


class ResourceDetailPageTestsBase(DbTestCase):
    def setUp(self):
        super().setUp()
        self.room = self.db.add_resource("Room A", "Rooms")
        self.detail = lambda uid, rid=None: self.call("get", f"/api/resources/{rid or self.room}/detail", uid)


class AppointmentTestsBase(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute("INSERT INTO professor_profiles (user_id, expertise, bio) VALUES (%s, %s, %s)",
                        (self.professor, "Software testing, Requirements engineering", "Test automation"))
        self.prof2 = self.db.add_user("professor", "Dr Anan", "anan@ku.th")
        self.db.execute("INSERT INTO professor_profiles (user_id, expertise, bio) VALUES (%s, %s, %s)",
                        (self.prof2, "Databases", "Schema design"))

    def ask(self, uid=None, prof=None, **extra):
        body = {"professor_id": prof or self.professor, "topic": "Testing strategy for our lab system",
                "details": "We have no tests yet", "start_time": at(3, 10).isoformat(), **extra}
        return self.call("post", "/api/appointments", uid or self.student, body)

    def decide(self, appt, decision, uid=None, **extra):
        return self.call("post", f"/api/appointments/{appt}/decide", uid or self.professor, {"decision": decision, **extra})

    def mine(self, uid=None):
        return self.call("get", "/api/appointments/mine", uid or self.student).get_json()["appointments"]

    def inbox(self, uid=None):
        return self.call("get", "/api/appointments/inbox", uid or self.professor).get_json()["appointments"]

    def titles(self, uid):
        return [n["title"] for n in self.call("get", "/api/notifications", uid).get_json()["notifications"]]
