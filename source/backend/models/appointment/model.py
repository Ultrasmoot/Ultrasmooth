# A student picks a professor (by name or by what they are good at), writes their own topic and
# asks for a 30-minute slot; the professor accepts or declines (the reason is optional). 
import datetime

from database.db import get_connection
from services.events import service as events

DURATION_MINUTES = 30
MAX_PENDING = 3          # open requests one student may have at the same time
MIN_TOPIC, MAX_TOPIC = 3, 100
MAX_DETAILS = 500
MAX_REASON = 255
MAX_DAYS_AHEAD = 120


class ValidationError(Exception):
    pass


from models.appointment.now_text import _now, _text, _parse_start, AppointmentModelNowText  # noqa: E402
from models.appointment.list_for_student_list_for_professor import AppointmentModelListForStudentListForProfessor  # noqa: E402
from models.appointment.cancel import AppointmentModelCancel  # noqa: E402


class AppointmentModel(AppointmentModelNowText, AppointmentModelListForStudentListForProfessor, AppointmentModelCancel):
    # ---------- the professor answers ----------
    @classmethod
    def decide(cls, appt_id: int, professor_id: int, decision: str, reason=None):
        if decision not in ("accept", "decline"):
            raise ValidationError("decision must be 'accept' or 'decline'.")
        reason = _text(reason, "Reason", 0, MAX_REASON) if decision == "decline" else None
        now = _now()
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True, buffered=True)
            # Lock the professor first: two accepts for the same professor are handled one at a time
            cur.execute("SELECT id FROM users WHERE id = %s FOR UPDATE", (professor_id,))
            cur.execute("SELECT * FROM appointments WHERE id = %s FOR UPDATE", (appt_id,))
            appt = cur.fetchone()
            if not appt or appt["professor_id"] != professor_id:
                raise ValidationError("Appointment not found.")
            if appt["status"] != "Pending":
                raise ValidationError(f"This request was already {appt['status'].lower()}.")
            if decision == "accept":
                if appt["start_time"] <= now:
                    raise ValidationError("This time has already passed, so the request can no longer be accepted.")
                cur.execute(
                    """SELECT COUNT(*) AS n FROM appointments
                       WHERE professor_id = %s AND status = 'Accepted' AND id <> %s
                         AND start_time < %s AND end_time > %s""",
                    (professor_id, appt_id, appt["end_time"], appt["start_time"]),
                )
                if cur.fetchone()["n"]:
                    raise ValidationError("You already have an accepted appointment that overlaps this time.")
            cur.execute(
                "UPDATE appointments SET status = %s, decision_reason = %s, decided_at = %s WHERE id = %s",
                ("Accepted" if decision == "accept" else "Declined", reason, now, appt_id),
            )
            events.appointment_decided(conn, appt_id, professor_id)
            conn.commit()
            return cls._get(cur, appt_id)
        except ValidationError:
            conn.rollback()
            raise
        finally:
            conn.close()
