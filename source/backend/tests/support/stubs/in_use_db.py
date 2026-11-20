from support.stubs.booking_cursor import Cur
from support.stubs.maintenance_base import Conn, DB
from support.stubs.checkin_sql_write import _norm


class Cur(Cur):
    def execute(self, sql, params=()):
        q, p = _norm(sql), list(params or ())
        if q.startswith("insert into bookings (resource_id, requester_id, start_time, end_time, purpose)"):
            db = self.db
            bid = db._bid
            db._bid += 1
            db.bookings[bid] = {"id": bid, "resource_id": p[0], "requester_id": p[1], "start_time": p[2],
                                "end_time": p[3], "purpose": p[4], "status": "Pending", "decided_by": None,
                                "decided_at": None, "decision_reason": None,
                                "checked_in_at": None, "checked_out_at": None}
            self._rows, self.rowcount, self.lastrowid = [], 0, bid
        else:
            super().execute(sql, params)


class Conn(Conn):
    def cursor(self, dictionary=False):
        return Cur(self.db)


class DB(DB):
    def connection(self):
        return Conn(self)
