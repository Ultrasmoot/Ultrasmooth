# fake cursor for booking decision tests, extending the check in fake
from support.stubs.checkin_cursor import Cur
from support.stubs.checkin_sql_write import ADMIN, STUDENT, _norm
import datetime

from support.stubs.booking_sql import CurBookings

NOW = datetime.datetime(2026, 10, 9, 10, 0, 0)


class Cur(CurBookings, Cur):
    def execute(self, sql, params=()):
        db, q, p = self.db, _norm(sql), list(params or ())
        if self._select_bookings(q, p):
            return
        if q.startswith("select status from resources where id = %s"):
            self._rows = [(db.resources[p[0]]["status"],)]
        elif q.startswith("select * from bookings where id = %s for update"):
            b = db.bookings.get(p[0])
            self._rows = [dict(b)] if b else []
        elif q.startswith("select count(*) from bookings where resource_id = %s and status in"):
            # _has_conflict parameters resource ID, statuses, end, start, optional excluded ID
            marks = q.split("status in (")[1].split(")")[0].count("%s")
            rid, statuses, (end, start) = p[0], p[1:1 + marks], p[1 + marks:3 + marks]
            exclude = p[3 + marks] if "and id != %s" in q else None
            n = sum(1 for b in db.bookings.values()
                    if b["resource_id"] == rid and b["status"] in statuses
                    and b["start_time"] < end and b["end_time"] > start and b["id"] != exclude)
            self._rows = [(n,)]
        elif q.startswith("update bookings set status=%s, decided_by=%s, decided_at=now(), decision_reason=%s"):
            status, admin, reason, bid = p
            b = db.bookings[bid]
            self.rowcount = 0
            if b["status"] == "Pending":
                b.update(status=status, decided_by=admin, decided_at=NOW, decision_reason=reason)
                self.rowcount = 1
            self._rows = []
        else:
            super().execute(sql, params)