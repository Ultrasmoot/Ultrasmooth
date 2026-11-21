import models.booking.model as _m

class BookingModelHasConflictGet:
    # conflict check
    @staticmethod
    def _has_conflict(conn, resource_id: int, start, end, exclude_booking_id: int = None,
                      statuses=("Pending", "Approved")) -> bool:
        # only Pending and Approved bookings block a slot. 
        # Rejected bookings free it. Overlap checks prevent double booking
        cur = conn.cursor()
        marks = ", ".join(["%s"] * len(statuses))
        sql = f"""SELECT COUNT(*) FROM bookings
                 WHERE resource_id = %s AND status IN ({marks})
                   AND start_time < %s AND end_time > %s"""
        params = [resource_id, *statuses, end, start]
        if exclude_booking_id:
            sql += " AND id != %s"
            params.append(exclude_booking_id)
        cur.execute(sql, tuple(params))
        return cur.fetchone()[0] > 0

    # lookups
    @staticmethod
    def get(booking_id: int):
        conn = _m.get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(_m._SELECT_WITH_NAMES + " WHERE b.id = %s", (booking_id,))
            return cur.fetchone()
        finally:
            conn.close()

    @staticmethod
    def list_mine(user_id: int):
        # a requester's own bookings and their current status
        conn = _m.get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                _m._SELECT_WITH_NAMES + " WHERE b.requester_id = %s ORDER BY b.start_time DESC",
                (user_id,),
            )
            return cur.fetchall()
        finally:
            conn.close()
