import datetime
import services.housekeeping.service as _m

def _now():
    return datetime.datetime.now()

# auto check-out
def _overdue_ids(now, grace_minutes):
    cutoff = now - datetime.timedelta(minutes=grace_minutes)
    conn = _m.get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """SELECT id FROM bookings
               WHERE status = 'Approved' AND checked_in_at IS NOT NULL
                 AND checked_out_at IS NULL AND end_time <= %s ORDER BY id""",
            (cutoff,),
        )
        return [r["id"] for r in cur.fetchall()]
    finally:
        conn.close()

def _close_one(booking_id, now, grace_minutes):
    # checks one overdue booking out. Returns True if this call did it
    cutoff = now - datetime.timedelta(minutes=grace_minutes)
    conn = _m.get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT resource_id FROM bookings WHERE id = %s", (booking_id,))
        row = cur.fetchone()
        if not row:
            return False
        resource_id = row["resource_id"]
        resource, booking = _m.lock_resource_then_booking(cur, resource_id, booking_id)
        # Re-check under the lock: the user may have checked out a moment ago
        if (not booking or booking["status"] != "Approved" or not booking["checked_in_at"]
                or booking["checked_out_at"] or booking["end_time"] > cutoff):
            conn.rollback()
            return False
        cur.execute("UPDATE bookings SET checked_out_at = %s WHERE id = %s AND checked_out_at IS NULL",
                    (now, booking_id))
        if cur.rowcount == 0:
            conn.rollback()
            return False
        # Free the resource only if it is still "In Use" and nobody else is checked in.
        # (If it went into Maintenance meanwhile it stays blocked.)
        if resource and resource["status"] == "In Use":
            cur.execute(
                """SELECT COUNT(*) AS n FROM bookings
                   WHERE resource_id = %s AND id <> %s AND status = 'Approved'
                     AND checked_in_at IS NOT NULL AND checked_out_at IS NULL""",
                (resource_id, booking_id),
            )
            if cur.fetchone()["n"] == 0:
                cur.execute("UPDATE resources SET status = 'Available' WHERE id = %s", (resource_id,))
        _m.events.checkout_auto(conn, booking_id)
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
