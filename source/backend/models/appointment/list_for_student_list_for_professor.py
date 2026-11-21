import datetime
import models.appointment.model as _m

class AppointmentModelListForStudentListForProfessor:
    # ---------- lists ----------
    @staticmethod
    def list_for_student(student_id: int):
        conn = _m.get_connection()
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
        conn = _m.get_connection()
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

    # ---------- a student asks ----------
    @classmethod
    def request(cls, student_id: int, data: dict):
        topic = _m._text(data.get("topic"), "Topic", _m.MIN_TOPIC, _m.MAX_TOPIC, required=True)
        details = _m._text(data.get("details"), "Details", 0, _m.MAX_DETAILS)
        now = _m._now()
        start = _m._parse_start(data.get("start_time"), now)
        end = start + datetime.timedelta(minutes=_m.DURATION_MINUTES)
        pid = data.get("professor_id")
        if isinstance(pid, bool) or not isinstance(pid, (int, str)) or not str(pid).strip().isdigit():
            raise _m.ValidationError("Please choose a professor.")
        pid = int(pid)

        conn = _m.get_connection()
        try:
            cur = conn.cursor(dictionary=True, buffered=True)
            # Lock the student's row: two requests sent at once cannot both slip under the limit.
            cur.execute("SELECT id FROM users WHERE id = %s FOR UPDATE", (student_id,))
            cur.execute("SELECT id FROM users WHERE id = %s AND role = 'professor' AND is_active = 1", (pid,))
            if not cur.fetchone():
                raise _m.ValidationError("The selected professor does not exist.")
            cur.execute(
                "SELECT COUNT(*) AS n FROM appointments WHERE student_id = %s AND status = 'Pending' AND start_time > %s",
                (student_id, now),
            )
            if cur.fetchone()["n"] >= _m.MAX_PENDING:
                raise _m.ValidationError(
                    f"You already have {_m.MAX_PENDING} pending requests. Cancel one or wait for an answer."
                )
            cur.execute(
                """SELECT COUNT(*) AS n FROM appointments
                   WHERE student_id = %s AND professor_id = %s AND status IN ('Pending', 'Accepted')
                     AND start_time < %s AND end_time > %s""",
                (student_id, pid, end, start),
            )
            if cur.fetchone()["n"]:
                raise _m.ValidationError("You already have a request with this professor at that time.")
            cur.execute(
                """INSERT INTO appointments (student_id, professor_id, topic, details, start_time, end_time, status, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, 'Pending', %s)""",
                (student_id, pid, topic, details, start, end, now),
            )
            new_id = cur.lastrowid
            _m.events.appointment_requested(conn, new_id)
            conn.commit()
            return cls._get(cur, new_id)
        except _m.ValidationError:
            conn.rollback()
            raise
        finally:
            conn.close()
