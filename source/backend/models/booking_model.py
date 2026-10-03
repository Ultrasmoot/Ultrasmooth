import datetime
import mysql.connector
from database.db import get_connection

VALID_DECISIONS = {"approve": "Approved", "reject": "Rejected"}
REQUIRED_FIELDS = ["resource_id", "start_time", "end_time", "purpose"]
MAX_PURPOSE_LENGTH = 255  # limit bookings purpose to VARCHAR(255)

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

    @staticmethod
    def _parse_datetime(value, field_name):
        try:
            parsed = datetime.datetime.fromisoformat(str(value).strip())
        except (TypeError, ValueError):
            raise ValidationError(f"{field_name} must be a valid date/time.")

        # Convert timezone to local time
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone().replace(tzinfo=None)

        return parsed

    @classmethod
    def _validate(cls, data: dict):
        for field in REQUIRED_FIELDS:
            if not data.get(field):
                raise ValidationError(f"{field} is required.")

        try:
            resource_id = int(data["resource_id"])
        except (TypeError, ValueError):
            raise ValidationError("resource_id must be a valid resource.")

        purpose = str(data["purpose"]).strip()
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

    # Check booking conflict
    @staticmethod
    def _has_conflict(conn, resource_id: int, start, end, exclude_booking_id: int = None) -> bool:
        """Check booking conflicts."""
        cur = conn.cursor()
        sql = """SELECT COUNT(*) FROM bookings
                 WHERE resource_id = %s AND status IN ('Pending','Approved')
                   AND start_time < %s AND end_time > %s"""
        params = [resource_id, end, start]
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
            if resource["status"] != "Available":
                raise ValidationError(
                    f"This resource is currently {resource['status']} and cannot be booked."
                )

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
    def decide(cls, booking_id: int, decision: str, admin_id: int):
        if decision not in VALID_DECISIONS:
            raise ValidationError("decision must be 'approve' or 'reject'.")

        booking = cls.get(booking_id)
        if not booking:
            raise ValidationError("Booking not found.")
        if booking["status"] != "Pending":
            raise ValidationError(f"This booking was already {booking['status'].lower()}.")

        conn = get_connection()
        try:
            cur = conn.cursor()
            # prevent 2 admins overwrite each other
            cur.execute(
                """UPDATE bookings SET status=%s, decided_by=%s, decided_at=NOW()
                   WHERE id=%s AND status='Pending'""",
                (VALID_DECISIONS[decision], admin_id, booking_id),
            )
            changed = cur.rowcount
            conn.commit()
        finally:
            conn.close()

        if changed == 0:
            latest = cls.get(booking_id)
            status = latest["status"].lower() if latest else "decided"
            raise ValidationError(f"This booking was already {status}.")
        return cls.get(booking_id)
