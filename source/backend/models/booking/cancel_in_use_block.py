import datetime
import models.booking.model as _m

class BookingModelCancelInUseBlock:
    # cancel (requester withdraws)
    @classmethod
    def cancel(cls, booking_id: int, requester_id: int):
        # users can cancel pending or approved bookings before check-in
        # after check-in, they must check out. Cancelled bookings free the slot
        booking = cls.get(booking_id)
        if not booking or booking["requester_id"] != requester_id:
            raise _m.ValidationError("Booking not found.")

        conn = _m.get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            # Same lock order as create()/decide() the resource row first, then the booking
            _, current = _m.lock_resource_then_booking(cur, booking["resource_id"], booking_id, "id")
            if not current or current["requester_id"] != requester_id:
                raise _m.ValidationError("Booking not found.")
            if current["status"] not in ("Pending", "Approved"):
                raise _m.ValidationError(
                    f"Only a pending or approved booking can be cancelled (this one is {current['status'].lower()})."
                )
            if current["checked_in_at"]:
                raise _m.ValidationError("You have already checked in, so please check out instead of cancelling.")
            now = datetime.datetime.now()
            if current["end_time"] <= now:
                raise _m.ValidationError("This booking has already ended, so it cannot be cancelled.")

            cur.execute(
                "UPDATE bookings SET status = 'Cancelled', cancelled_at = %s "
                "WHERE id = %s AND status = %s AND checked_in_at IS NULL",
                (now, booking_id, current["status"]),
            )
            if cur.rowcount == 0:
                raise _m.ValidationError("This booking was changed just now. Please refresh and try again.")
            _m.events.booking_cancelled(conn, booking_id, current["status"])
            conn.commit()
        except _m.ValidationError:
            conn.rollback()
            raise
        finally:
            conn.close()
        return cls.get(booking_id)

    @classmethod
    def _in_use_block(cls, conn, resource_id: int, start):
        # In Use blocks bookings until the current session ends
        # If no one is checked in, nearby bookings are blocked because the end time is unknown
        now = datetime.datetime.now()
        session_end = cls._active_session_end(conn, resource_id)
        if session_end is not None:
            if session_end > now and start < session_end:
                return (
                    f"This resource is in use until {session_end:%d %b %H:%M}. "
                    "Please choose a start time after that."
                )
            return None
        if start < now + datetime.timedelta(minutes=_m.EARLY_CHECKIN_MINUTES):
            return (
                "This resource is currently marked In Use. Please choose a later "
                "start time or ask an administrator."
            )
        return None
