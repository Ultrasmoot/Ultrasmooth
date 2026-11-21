# INSERT / UPDATE / DELETE statements of the fake check-in cursor
import copy
import datetime
import support.stubs.maintenance_cursor as _c
from support.stubs.maintenance_sql import _norm  # noqa: F401


class CurWrite:
    def _checkin_write_sql(self, q, p):
        db = self.db
        if q.startswith("update checkin_codes set consumed_at = %s where booking_id"):
            for c in db.codes.values():
                if c["booking_id"] == p[1] and c["consumed_at"] is None:
                    c["consumed_at"] = p[0]
        elif q.startswith("insert into checkin_codes"):
            cid = db._cid
            db._cid += 1
            db.codes[cid] = {"id": cid, "booking_id": p[0], "user_id": p[1], "code_hash": p[2],
                             "expires_at": p[3], "attempts": 0, "consumed_at": None, "created_at": p[4]}
            self.lastrowid = cid
        elif q.startswith("delete from checkin_codes where id"):
            db.codes.pop(p[0], None)
        elif q.startswith("update checkin_codes set attempts"):
            db.codes[p[1]]["attempts"] = p[0]
        elif q.startswith("update checkin_codes set consumed_at = %s where id"):
            db.codes[p[1]]["consumed_at"] = p[0]
        elif q.startswith("update bookings set checked_in_at"):
            db.bookings[p[1]]["checked_in_at"] = p[0]
        elif q.startswith("update bookings set checked_out_at"):
            db.bookings[p[1]]["checked_out_at"] = p[0]
        elif q.startswith("update resources set status = 'in use'"):
            db.resources[p[0]]["status"] = "In Use"
        else:
            return False
        return True


ADMIN, STUDENT, OTHER_STUDENT, PROFESSOR = 1, 2, 3, 4


PRINTER, SCOPE, ARCHIVED = 10, 11, 12


class FakeDB:
    """In-memory stand-in for the MySQL tables these tests touch."""

    def __init__(self):
        self.users = {
            ADMIN: {"id": ADMIN, "full_name": "Demo Admin", "email": "admin@ku.th", "role": "admin", "is_active": 1},
            STUDENT: {"id": STUDENT, "full_name": "Demo Student", "email": "s1@ku.th", "role": "undergrad_student", "is_active": 1},
            OTHER_STUDENT: {"id": OTHER_STUDENT, "full_name": "Other Student", "email": "s2@ku.th", "role": "phd_student", "is_active": 1},
            PROFESSOR: {"id": PROFESSOR, "full_name": "Aj. Somchai", "email": "p@ku.th", "role": "professor", "is_active": 1},
        }

        def res(rid, name, archived=0):
            return {"id": rid, "resource_code": f"RES-{rid:04d}", "name": name, "type": "Equipment",
                    "category": "Fabrication", "location": "Lab A", "owner": "Demo Admin",
                    "status": "Available", "is_archived": archived}

        self.resources = {PRINTER: res(PRINTER, "3D Printer"), SCOPE: res(SCOPE, "Oscilloscope"),
                          ARCHIVED: res(ARCHIVED, "Old Scanner", archived=1)}
        self.records = {}
        self._next = 1
        self._clock = datetime.datetime(2026, 10, 1, 9, 0, 0)

    def connection(self):
        return FakeConn(self)

    def status_of(self, rid):
        return self.resources[rid]["status"]


class FakeConn:
    def __init__(self, db):
        self.db = db
        self._snap = (copy.deepcopy(db.resources), copy.deepcopy(db.records))

    def cursor(self, dictionary=False):
        return _c.FakeCursor(self.db)

    def commit(self):
        self._snap = (copy.deepcopy(self.db.resources), copy.deepcopy(self.db.records))

    def rollback(self):
        self.db.resources, self.db.records = copy.deepcopy(self._snap[0]), copy.deepcopy(self._snap[1])

    def close(self):
        pass
