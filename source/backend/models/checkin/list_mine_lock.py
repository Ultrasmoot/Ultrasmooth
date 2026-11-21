# list_mine_lock: part of models.checkin.model 
# the public names are still imported from models.checkin.model
import datetime
import models.checkin.model as _m

class CheckinModelListMineLock:
    # list
    @staticmethod
    def list_mine(user_id: int):
        now = _m._now()
        since = now - datetime.timedelta(days=_m.DONE_HISTORY_DAYS)
        conn = _m.get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                _m._SELECT + """ WHERE b.requester_id = %s AND b.status = 'Approved'
                              AND b.end_time >= %s ORDER BY b.start_time ASC""",
                (user_id, since),
            )
            rows = cur.fetchall()
        finally:
            conn.close()

        in_use, ready, done = [], [], []
        for b in rows:
            if b["checked_in_at"] and not b["checked_out_at"]:
                in_use.append(b)
            elif b["checked_out_at"]:
                done.append(b)
            elif b["end_time"] > now:
                b["block_reason"] = _m.block_reason(b, b["resource_status"], now)
                ready.append(b)
        done.sort(key=lambda b: b["checked_out_at"], reverse=True)
        return {"in_use": in_use, "ready": ready, "done": done[:_m.DONE_LIMIT]}

    # internal
    @staticmethod
    def _lock(conn, booking_id: int, user_id: int):
        """Lock the resource row, then the booking row (locking reads, so the
        latest committed state is seen), and make sure the booking is the caller's.
        Same lock order as everywhere else: resource first."""
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT resource_id FROM bookings WHERE id = %s", (booking_id,))
        row = cur.fetchone()
        if not row:
            raise _m.ValidationError("Booking not found.")
        resource, booking = _m.lock_resource_then_booking(
            cur, row["resource_id"], booking_id, booking_sql=_m._SELECT + " WHERE b.id = %s FOR UPDATE")
        if not booking or booking["requester_id"] != user_id:
            raise _m.ValidationError("Booking not found.")
        return cur, resource, booking
