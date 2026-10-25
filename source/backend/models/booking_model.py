import datetime
import mysql.connector
from database.db import get_connection
from models.checkin_model import EARLY_CHECKIN_MINUTES

VALID_DECISIONS = {"approve": "Approved", "reject": "Rejected"}
REQUIRED_FIELDS = ["resource_id", "start_time", "end_time", "purpose"]
MAX_PURPOSE_LENGTH = 255  # limit bookings purpose to VARCHAR(255)
MAX_REASON_LENGTH = 255  # limit bookings decision reason VARCHAR(255)

# returns the resource name and requester name/email along with booking
_SELECT_WITH_NAMES = """
    SELECT b.*,
           r.name      AS resource_name,
           u.full_name AS requester_name,
           u.email     AS requester_email
    FROM bookings b
    JOIN resources r ON r.id = b.resource_id
    JOIN users u     ON u.id = b.requester_id
"""


class ValidationError(Exception):
    pass


class BookingModel:
    # validation
    @staticmethod
    def _parse_datetime(value, field_name):
        try:
            parsed = datetime.datetime.fromisoformat(str(value).strip())
        except (TypeError, ValueError):
            raise ValidationError(f"{field_name} must be a valid date/time.")

        # Convert timezone to local time
        if parsed.tzinfo is not None:
            try:
                parsed = parsed.astimezone().replace(tzinfo=None)
            except (OverflowError, OSError, ValueError):
                raise ValidationError(f"{field_name} must be a valid date/time.")
        return parsed

    @classmethod
    def _validate(cls, data: dict):
        for field in REQUIRED_FIELDS:
            if not data.get(field):
                raise ValidationError(f"{field} is required.")

        try:
            resource_id = int(data["resource_id"])
        except (TypeError, ValueError, OverflowError):  # overflowError
            raise ValidationError("resource_id must be a valid resource.")

        if not isinstance(data["purpose"], str):
            raise ValidationError("purpose must be text.")
        purpose = data["purpose"].strip()
        if not purpose:
            raise ValidationError("purpose is required.")
        if len(purpose) > MAX_PURPOSE_LENGTH:
            raise ValidationError(
                f"purpose must be at most {MAX_PURPOSE_LENGTH} characters "
                f"(currently {len(purpose)})."
            )

        start = cls._parse_datetime(data["start_time"], "start_time")
        end = cls._parse_datetime(data["end_time"], "end_time")

        if end <= start:
            raise ValidationError("end_time must be after start_time.")
        if start < datetime.datetime.now():
            raise ValidationError("start_time cannot be in the past.")

        return resource_id, start, end, purpose

    # In Use rule
    @staticmethod
    def _active_session_end(conn, resource_id: int):
        # end time of checked in + none checked out
        cur = conn.cursor()
        cur.execute(
            """SELECT MAX(end_time) FROM bookings
               WHERE resource_id = %s AND status = 'Approved'
                 AND checked_in_at IS NOT NULL AND checked_out_at IS NULL""",
            (resource_id,),
        )
        row = cur.fetchone()
        return row[0] if row else None

    @classmethod
    def _in_use_block(cls, conn, resource_id: int, start):
        now = datetime.datetime.now()
        session_end = cls._active_session_end(conn, resource_id)
        if session_end is not None:
            if session_end > now and start < session_end:
                return (
                    f"This resource is in use until {session_end:%d %b %H:%M}. "
                    "Please choose a start time after that."
                )
            return None
        if start < now + datetime.timedelta(minutes=EARLY_CHECKIN_MINUTES):
            return (
                "This resource is currently marked In Use. Please choose a later "
                "start time or ask an administrator."
            )
        return None

    # conflict check (SRS-3)
    @staticmethod
    def _has_conflict(conn, resource_id: int, start, end, exclude_booking_id: int = None,
                      statuses=("Pending", "Approved")) -> bool:
        # booking only blocks the slot when it is pending or approved
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
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(_SELECT_WITH_NAMES + " WHERE b.id = %s", (booking_id,))
            return cur.fetchone()
        finally:
            conn.close()

    @staticmethod
    def list_mine(user_id: int):
    # US-4: a requester's own bookings and their current status
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                _SELECT_WITH_NAMES + " WHERE b.requester_id = %s ORDER BY b.start_time DESC",
                (user_id,),
            )
            return cur.fetchall()
        finally:
            conn.close()

    @staticmethod
    def list_pending():
        # US-5: admin review queue
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                _SELECT_WITH_NAMES + " WHERE b.status = 'Pending' ORDER BY b.start_time ASC"
            )
            return cur.fetchall()
        finally:
            conn.close()

    @staticmethod
    def list_history():
        # Admin history: requests already decided
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                _SELECT_WITH_NAMES
                + " WHERE b.status <> 'Pending' ORDER BY b.decided_at DESC, b.id DESC"
            )
            return cur.fetchall()
        finally:
            conn.close()

    # Create booking
    @classmethod
    def create(cls, data: dict, requester_id: int):
        resource_id, start, end, purpose = cls._validate(data)
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)

            # Lock resource during booking
            cur.execute(
                "SELECT status, is_archived FROM resources WHERE id = %s FOR UPDATE",
                (resource_id,),
            )
            resource = cur.fetchone()
            if not resource or resource["is_archived"]:
                raise ValidationError("The selected resource does not exist.")
            if resource["status"] == "Maintenance":
                raise ValidationError(
                    "This resource is currently under Maintenance and cannot be booked."
                )
            if resource["status"] == "In Use":
                in_use_reason = cls._in_use_block(conn, resource_id, start)
                if in_use_reason:
                    raise ValidationError(in_use_reason)

            if cls._has_conflict(conn, resource_id, start, end):
                raise ValidationError("This resource is already booked for the selected time.")

            cur.execute(
                """INSERT INTO bookings (resource_id, requester_id, start_time, end_time, purpose)
                   VALUES (%s, %s, %s, %s, %s)""",
                (resource_id, requester_id, start, end, purpose),
            )
            new_id = cur.lastrowid
            conn.commit()
        except ValidationError:
            conn.rollback()
            raise
        except mysql.connector.IntegrityError:
            conn.rollback()
            raise ValidationError("The selected resource does not exist.")
        except mysql.connector.DataError:
            conn.rollback()
            raise ValidationError("Some of the submitted values are too long or invalid.")
        finally:
            conn.close()
        return cls.get(new_id)
        
    # US-5: approve/reject
    @classmethod
    def decide(cls, booking_id: int, decision: str, admin_id: int, reason=None):
        if not isinstance(decision, str) or decision not in VALID_DECISIONS:
            raise ValidationError("decision must be 'approve' or 'reject'.")
        if decision == "reject":
            if reason is not None and not isinstance(reason, str):
                raise ValidationError("reason must be text.")
            reason = (reason or "").strip() or None
            if reason and len(reason) > MAX_REASON_LENGTH:
                raise ValidationError(
                    f"reason must be at most {MAX_REASON_LENGTH} characters (currently {len(reason)})."
                )
        else:
            reason = None

        booking = cls.get(booking_id)
        if not booking:
            raise ValidationError("Booking not found.")

        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT status, is_archived FROM resources WHERE id = %s FOR UPDATE",
                (booking["resource_id"],),
            )
            resource = cur.fetchone()
            cur.execute("SELECT * FROM bookings WHERE id = %s FOR UPDATE", (booking_id,))
            current = cur.fetchone()
            if not current:
                raise ValidationError("Booking not found.")
            if current["status"] != "Pending":
                raise ValidationError(f"This booking was already {current['status'].lower()}.")

            if decision == "approve":
                if current["start_time"] < datetime.datetime.now():
                    raise ValidationError(
                        "This booking has already started, so it can no longer be approved."
                    )
                if not resource or resource["is_archived"]:
                    raise ValidationError(
                        "This resource has been archived, so the booking cannot be approved."
                    )
                if resource["status"] == "Maintenance":
                    raise ValidationError(
                        "This resource is under Maintenance, so the booking cannot be approved."
                    )
                if resource["status"] == "In Use":
                    in_use_reason = cls._in_use_block(conn, current["resource_id"], current["start_time"])
                    if in_use_reason:
                        raise ValidationError(in_use_reason)
                if cls._has_conflict(
                    conn, current["resource_id"], current["start_time"], current["end_time"],
                    exclude_booking_id=booking_id, statuses=("Approved",),
                ):
                    raise ValidationError(
                        "This resource is already booked for part of this time, so the booking cannot be approved."
                    )

            cur.execute(
                """UPDATE bookings SET status=%s, decided_by=%s, decided_at=NOW(), decision_reason=%s
                   WHERE id=%s AND status='Pending'""",
                (VALID_DECISIONS[decision], admin_id, reason, booking_id),
            )
            if cur.rowcount == 0:
                raise ValidationError("This booking was already decided.")
            conn.commit()
        except ValidationError:
            conn.rollback()
            raise
        finally:
            conn.close()
        return cls.get(booking_id)
