from support.stubs.booking_cursor import Cur
from support.stubs.maintenance_base import Conn, DB
from support.stubs.checkin_sql_write import _norm
import datetime



class Cur(Cur):
    statements = []  # every statement sent, test check row is locked

    def execute(self, sql, params=()):
        q, p = _norm(sql), list(params or ())
        Cur.statements.append(q)
        if q.startswith("select count(*) from bookings where resource_id = %s and status in ('pending','approved')"):
            now = datetime.datetime.now()
            n = sum(1 for b in self.db.bookings.values()
                    if b["resource_id"] == p[0] and b["status"] in ("Pending", "Approved")
                    and b["end_time"] > now and not b["checked_out_at"])
            self._rows, self.rowcount = [(n,)], 0
        elif q.startswith("update resources set is_archived = 1 where id"):
            self.db.resources[p[0]]["is_archived"] = 1
            self._rows, self.rowcount = [], 1
        else:
            super().execute(sql, params)


class Conn(Conn):
    def cursor(self, dictionary=False):
        return Cur(self.db)


class DB(DB):
    def connection(self):
        return Conn(self)
