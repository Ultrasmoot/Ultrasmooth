import datetime
import mysql.connector
import models.booking.model as _m

class BookingModelCreateParseDatetime:
    @classmethod
    def create(cls, data: dict, requester_id: int):
        resource_id, start, end, purpose = cls._validate(data)
        conn = _m.get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            # locks the resource to prevent simultaneous bookings and avoid booking conflicts
            cur.execute(
                "SELECT status, is_archived FROM resources WHERE id = %s FOR UPDATE",
                (resource_id,),
            )
            resource = cur.fetchone()
            if not resource or resource["is_archived"]:
                raise _m.ValidationError("The selected resource does not exist.")
            # In Use allows bookings after the current session ends. Maintenance blocks all bookings.
            if resource["status"] == "Maintenance":
                raise _m.ValidationError(
                    "This resource is currently under Maintenance and cannot be booked."
                )
            if resource["status"] == "In Use":
                in_use_reason = cls._in_use_block(conn, resource_id, start)
                if in_use_reason:
                    raise _m.ValidationError(in_use_reason)

            if cls._has_conflict(conn, resource_id, start, end):
                raise _m.ValidationError("This resource is already booked for the selected time.")

            cur.execute(
                """INSERT INTO bookings (resource_id, requester_id, start_time, end_time, purpose)
                   VALUES (%s, %s, %s, %s, %s)""",
                (resource_id, requester_id, start, end, purpose),
            )
            new_id = cur.lastrowid
            _m.events.booking_submitted(conn, new_id)   # Iteration 5: same transaction as the INSERT
            conn.commit()
        except _m.ValidationError:
            conn.rollback()
            raise
        except mysql.connector.IntegrityError:
            conn.rollback()
            raise _m.ValidationError("The selected resource does not exist.")
        except mysql.connector.DataError:
            conn.rollback()
            raise _m.ValidationError("Some of the submitted values are too long or invalid.")
        finally:
            conn.close()
        return cls.get(new_id)

    # validation
    @staticmethod
    def _parse_datetime(value, field_name):
        try:
            parsed = datetime.datetime.fromisoformat(str(value).strip())
        except (TypeError, ValueError):
            raise _m.ValidationError(f"{field_name} must be a valid date/time.")
        # Converts timezone-aware dates to local time and 
        # keeps naive dates as local time to avoid comparison errors
        if parsed.tzinfo is not None:
            try:
                parsed = parsed.astimezone().replace(tzinfo=None)
            except (OverflowError, OSError, ValueError):
                raise _m.ValidationError(f"{field_name} must be a valid date/time.")
        return parsed
