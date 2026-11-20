# fake cursor SELECT queries for booking decision tests
from support.stubs.checkin_sql_write import ADMIN, FakeConn, FakeDB, OTHER_STUDENT, PRINTER, PROFESSOR, SCOPE, STUDENT
import copy
import datetime
import support.stubs.checkin_cursor as _c


class CurBookings:
    def _named(self, b):
        r, u = self.db.resources[b["resource_id"]], self.db.users[b["requester_id"]]
        return {**b, "resource_name": r["name"], "requester_name": u["full_name"], "requester_email": u["email"]}

    def _select_bookings(self, q, p):
        if not q.startswith("select b.*, r.name as resource_name, u.full_name as requester_name"):
            return False
        rows = list(self.db.bookings.values())
        if "where b.id = %s" in q:
            rows = [b for b in rows if b["id"] == p[0]]
        elif "where b.requester_id = %s" in q:
            rows = [b for b in rows if b["requester_id"] == p[0]]
        elif "where b.status = 'pending'" in q:
            rows = [b for b in rows if b["status"] == "Pending"]
        self._rows = [self._named(b) for b in rows]
        return True


NOW = datetime.datetime(2026, 10, 9, 10, 0, 0)


MIN = datetime.timedelta(minutes=1)


STUDENT, OTHER, ADMIN, PROFESSOR = STUDENT, OTHER_STUDENT, ADMIN, PROFESSOR


class BookingsDB(FakeDB):
    def __init__(self):
        super().__init__()
        self.bookings, self.codes, self._bid, self._cid = {}, {}, 1, 1

    def add_booking(self, rid=PRINTER, uid=STUDENT, start=NOW - 30 * MIN, end=NOW + 90 * MIN, status="Approved"):
        bid = self._bid
        self._bid += 1
        self.bookings[bid] = {"id": bid, "resource_id": rid, "requester_id": uid, "start_time": start,
                              "end_time": end, "purpose": "Print a part", "status": status,
                              "checked_in_at": None, "checked_out_at": None}
        return bid

    def connection(self):
        return Conn(self)


class Conn(FakeConn):
    def __init__(self, db):
        super().__init__(db)
        self._snap2 = (copy.deepcopy(db.bookings), copy.deepcopy(db.codes))

    def cursor(self, dictionary=False):
        return _c.Cur(self.db)

    def commit(self):
        super().commit()
        self._snap2 = (copy.deepcopy(self.db.bookings), copy.deepcopy(self.db.codes))

    def rollback(self):
        super().rollback()
        self.db.bookings, self.db.codes = copy.deepcopy(self._snap2[0]), copy.deepcopy(self._snap2[1])
