# check_out: part of models.checkin.model 
# the public names are still imported from models.checkin.model
import models.checkin.model as _m

class CheckinModelCheckOut:
    # check out
    @classmethod
    def check_out(cls, booking_id: int, user: dict):
        now = _m._now()
        conn = _m.get_connection()
        try:
            cur, resource, booking = cls._lock(conn, booking_id, user["id"])
            if not booking["checked_in_at"]:
                raise _m.ValidationError("You have not checked in to this booking.")
            if booking["checked_out_at"]:
                raise _m.ValidationError("You have already checked out.")
            cur.execute("UPDATE bookings SET checked_out_at = %s WHERE id = %s", (now, booking_id))
            # Free the resource only if it is still "In Use". 
            # If an admin has moved it to Maintenance -> the time is recorded but the resource must stay blocked.
            if resource["status"] == "In Use":
                cur.execute("UPDATE resources SET status = 'Available' WHERE id = %s", (resource["id"],))
            _m.events.checkout_done(conn, booking_id)
            conn.commit()
        except _m.ValidationError:
            conn.rollback()
            raise
        finally:
            conn.close()
        return cls.get(booking_id)
