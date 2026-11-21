# cancel: part of models.appointment.model (split so each file stays small). The public names are still imported from models.appointment.model.
import models.appointment.model as _m

class AppointmentModelCancel:
    # ---------- the student withdraws ----------
    @classmethod
    def cancel(cls, appt_id: int, student_id: int):
        conn = _m.get_connection()
        try:
            cur = conn.cursor(dictionary=True, buffered=True)
            cur.execute("SELECT professor_id FROM appointments WHERE id = %s", (appt_id,))
            row = cur.fetchone()
            if row:
                cur.execute("SELECT id FROM users WHERE id = %s FOR UPDATE", (row["professor_id"],))
            cur.execute("SELECT * FROM appointments WHERE id = %s FOR UPDATE", (appt_id,))
            appt = cur.fetchone()
            if not appt or appt["student_id"] != student_id:
                raise _m.ValidationError("Appointment not found.")
            if appt["status"] not in ("Pending", "Accepted"):
                raise _m.ValidationError(
                    f"Only a pending or accepted appointment can be cancelled (this one is {appt['status'].lower()}).")
            # A pending request may always be withdrawn; an accepted appointment only before it starts.
            if appt["status"] == "Accepted" and appt["start_time"] <= _m._now():
                raise _m.ValidationError("This appointment has already started or passed, so it cannot be cancelled.")
            cur.execute("UPDATE appointments SET status = 'Cancelled' WHERE id = %s", (appt_id,))
            _m.events.appointment_cancelled(conn, appt_id, was_status=appt["status"])
            conn.commit()
            return cls._get(cur, appt_id)
        except _m.ValidationError:
            conn.rollback()
            raise
        finally:
            conn.close()
