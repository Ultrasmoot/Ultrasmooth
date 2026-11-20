# The SQL the fake check in cursor understands bookings one-time codes


class CurSelect:
    def _checkin_select_sql(self, q, p):
        db = self.db
        if q.startswith("select resource_id from bookings where id"):
            b = db.bookings.get(p[0])
            self._rows = [{"resource_id": b["resource_id"]}] if b else []
        elif q.startswith("select b.*, r.name as resource_name") and "where b.id = %s" in q:
            b = db.bookings.get(p[0])
            self._rows = [self._joined(b)] if b else []
        elif q.startswith("select b.*, r.name as resource_name") and "b.requester_id = %s and b.status = 'approved'" in q:
            uid, since = p
            rows = [b for b in db.bookings.values()
                    if b["requester_id"] == uid and b["status"] == "Approved" and b["end_time"] >= since]
            self._rows = [self._joined(b) for b in sorted(rows, key=lambda b: b["start_time"])]
        elif q.startswith("select created_at from checkin_codes where booking_id"):
            rows = [c for c in db.codes.values() if c["booking_id"] == p[0]]
            self._rows = [{"created_at": max(rows, key=lambda c: c["id"])["created_at"]}] if rows else []
        elif q.startswith("select * from checkin_codes where booking_id"):
            rows = [c for c in db.codes.values()
                    if c["booking_id"] == p[0] and c["user_id"] == p[1] and c["consumed_at"] is None]
            self._rows = [dict(max(rows, key=lambda c: c["id"]))] if rows else []
        elif q.startswith("select max(end_time) from bookings where resource_id = %s"):
            ends = [b["end_time"] for b in db.bookings.values()
                    if b["resource_id"] == p[0] and b["status"] == "Approved"
                    and b["checked_in_at"] and not b["checked_out_at"]]
            self._rows = [(max(ends) if ends else None,)]
        else:
            return False
        return True
