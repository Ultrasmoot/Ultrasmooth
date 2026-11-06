# Students can request 30-minute appointments with professors.
import datetime

from database.db import get_connection
from services import events

DURATION_MINUTES = 30
MAX_PENDING = 3        # Maximum pending requests
MIN_TOPIC, MAX_TOPIC = 3, 100
MAX_DETAILS = 500
MAX_REASON = 255
MAX_DAYS_AHEAD = 120


class ValidationError(Exception):
    pass


def _now():
    return datetime.datetime.now()


def _text(value, name, minimum=0, maximum=500, required=False):
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ValidationError(f"{name} is required.")
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{name} must be text.")
    value = " ".join(value.split())
    if len(value) < minimum:
        raise ValidationError(f"{name} must be at least {minimum} characters.")
    if len(value) > maximum:
        raise ValidationError(f"{name} must be at most {maximum} characters.")
    return value


def _parse_start(value, now):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("A date and time is required.")
    try:
        start = datetime.datetime.fromisoformat(value.strip())
    except ValueError:
        raise ValidationError("The date and time is not valid.")
    if start.tzinfo is not None:
        start = start.astimezone().replace(tzinfo=None)
    start = start.replace(second=0, microsecond=0)
    if start <= now:
        raise ValidationError("The appointment must be in the future.")
    if start > now + datetime.timedelta(days=MAX_DAYS_AHEAD):
        raise ValidationError(f"The appointment must be within {MAX_DAYS_AHEAD} days.")
    return start


class AppointmentModel:

    # Professor directory
    @staticmethod
    def professors():
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True, buffered=True)
            cur.execute(
                """SELECT u.id, u.full_name, COALESCE(p.expertise, '') AS expertise,
                          COALESCE(p.bio, '') AS bio, p.photo_path
                   FROM users u LEFT JOIN professor_profiles p ON p.user_id = u.id
                   WHERE u.role = 'professor' AND u.is_active = 1 ORDER BY u.full_name"""
            )
            return cur.fetchall()
        finally:
            conn.close()

    # Appointment lists
    @staticmethod
    def list_for_student(student_id: int):
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True, buffered=True)
            cur.execute(
                """SELECT a.*, p.full_name AS professor_name, s.full_name AS student_name
                   FROM appointments a JOIN users p ON p.id = a.professor_id JOIN users s ON s.id = a.student_id
                   WHERE a.student_id = %s ORDER BY a.start_time DESC, a.id DESC""",
                (student_id,),
            )
            return cur.fetchall()
        finally:
            conn.close()

    @staticmethod
    def list_for_professor(professor_id: int):
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True, buffered=True)
            cur.execute(
                """SELECT a.*, p.full_name AS professor_name, s.full_name AS student_name
                   FROM appointments a JOIN users p ON p.id = a.professor_id JOIN users s ON s.id = a.student_id
                   WHERE a.professor_id = %s ORDER BY a.start_time ASC, a.id ASC""",
                (professor_id,),
            )
            return cur.fetchall()
        finally:
            conn.close()

    @staticmethod
    def _get(cur, appt_id):
        cur.execute(
            """SELECT a.*, p.full_name AS professor_name, s.full_name AS student_name
               FROM appointments a JOIN users p ON p.id = a.professor_id JOIN users s ON s.id = a.student_id
               WHERE a.id = %s""",
            (appt_id,),
        )
        return cur.fetchone()

    # a student asks 
    @classmethod
    def request(cls, student_id: int, data: dict):
        topic = _text(data.get("topic"), "Topic", MIN_TOPIC, MAX_TOPIC, required=True)
        details = _text(data.get("details"), "Details", 0, MAX_DETAILS)
        now = _now()
        start = _parse_start(data.get("start_time"), now)
        end = start + datetime.timedelta(minutes=DURATION_MINUTES)
        pid = data.get("professor_id")
        if isinstance(pid, bool) or not isinstance(pid, (int, str)) or not str(pid).strip().isdigit():
            raise ValidationError("Please choose a professor.")
        pid = int(pid)

        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True, buffered=True)
            # Prevent simultaneous requests from exceeding the limit.
            cur.execute("SELECT id FROM users WHERE id = %s FOR UPDATE", (student_id,))
            cur.execute("SELECT id FROM users WHERE id = %s AND role = 'professor' AND is_active = 1", (pid,))
            if not cur.fetchone():
                raise ValidationError("The selected professor does not exist.")
            cur.execute(
                "SELECT COUNT(*) AS n FROM appointments WHERE student_id = %s AND status = 'Pending' AND start_time > %s",
                (student_id, now),
            )
            if cur.fetchone()["n"] >= MAX_PENDING:
                raise ValidationError(
                    f"You already have {MAX_PENDING} pending requests. Cancel one or wait for an answer."
                )
            cur.execute(
                """SELECT COUNT(*) AS n FROM appointments
                   WHERE student_id = %s AND professor_id = %s AND status IN ('Pending', 'Accepted')
                     AND start_time < %s AND end_time > %s""",
                (student_id, pid, end, start),
            )
            if cur.fetchone()["n"]:
                raise ValidationError("You already have a request with this professor at that time.")
            cur.execute(
                """INSERT INTO appointments (student_id, professor_id, topic, details, start_time, end_time, status, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, 'Pending', %s)""",
                (student_id, pid, topic, details, start, end, now),
            )
            new_id = cur.lastrowid
            events.appointment_requested(conn, new_id)
            conn.commit()
            return cls._get(cur, new_id)
        except ValidationError:
            conn.rollback()
            raise
        finally:
            conn.close()

    # Professor's decision
    @classmethod
    def decide(cls, appt_id: int, professor_id: int, decision: str, reason=None):
        if decision not in ("accept", "decline"):
            raise ValidationError("decision must be 'accept' or 'decline'.")
        reason = _text(reason, "Reason", 0, MAX_REASON) if decision == "decline" else None
        now = _now()
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True, buffered=True)
            # Prevent simultaneous accepts from overlapping.
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

    # Student cancellation
    @classmethod
    def cancel(cls, appt_id: int, student_id: int):
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True, buffered=True)
            cur.execute("SELECT professor_id FROM appointments WHERE id = %s", (appt_id,))
            row = cur.fetchone()
            if row:
                cur.execute("SELECT id FROM users WHERE id = %s FOR UPDATE", (row["professor_id"],))
            cur.execute("SELECT * FROM appointments WHERE id = %s FOR UPDATE", (appt_id,))
            appt = cur.fetchone()
            if not appt or appt["student_id"] != student_id:
                raise ValidationError("Appointment not found.")
            if appt["status"] not in ("Pending", "Accepted"):
                raise ValidationError(
                    f"Only a pending or accepted appointment can be cancelled (this one is {appt['status'].lower()}).")
            # Pending requests can be cancelled anytime; accepted ones only before they start.
            if appt["status"] == "Accepted" and appt["start_time"] <= _now():
                raise ValidationError("This appointment has already started or passed, so it cannot be cancelled.")
            cur.execute("UPDATE appointments SET status = 'Cancelled' WHERE id = %s", (appt_id,))
            events.appointment_cancelled(conn, appt_id, was_status=appt["status"])
            conn.commit()
            return cls._get(cur, appt_id)
        except ValidationError:
            conn.rollback()
            raise
        finally:
            conn.close()
