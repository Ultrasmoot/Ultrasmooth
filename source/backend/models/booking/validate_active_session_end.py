import datetime
import models.booking.model as _m

class BookingModelValidateActiveSessionEnd:
    @classmethod
    def _validate(cls, data: dict):
        for field in _m.REQUIRED_FIELDS:
            if not data.get(field):
                raise _m.ValidationError(f"{field} is required.")

        try:
            resource_id = int(data["resource_id"])
        except (TypeError, ValueError, OverflowError):
            raise _m.ValidationError("resource_id must be a valid resource.")

        if not isinstance(data["purpose"], str):
            raise _m.ValidationError("purpose must be text.")
        purpose = data["purpose"].strip()
        if not purpose:
            raise _m.ValidationError("purpose is required.")
        if len(purpose) > _m.MAX_PURPOSE_LENGTH:
            raise _m.ValidationError(
                f"purpose must be at most {_m.MAX_PURPOSE_LENGTH} characters "
                f"(currently {len(purpose)})."
            )

        start = cls._parse_datetime(data["start_time"], "start_time")
        end = cls._parse_datetime(data["end_time"], "end_time")

        if end <= start:
            raise _m.ValidationError("end_time must be after start_time.")
        if start < datetime.datetime.now():
            raise _m.ValidationError("start_time cannot be in the past.")

        return resource_id, start, end, purpose

    # "In Use" rule
    @staticmethod
    def _active_session_end(conn, resource_id: int):
        # End time of the booking someone has checked in to and not yet checked
        # out of (the current user of the resource), or None if there is none
        cur = conn.cursor()
        cur.execute(
            """SELECT MAX(end_time) FROM bookings
               WHERE resource_id = %s AND status = 'Approved'
                 AND checked_in_at IS NOT NULL AND checked_out_at IS NULL""",
            (resource_id,),
        )
        row = cur.fetchone()
        return row[0] if row else None
