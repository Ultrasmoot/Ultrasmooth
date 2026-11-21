import datetime

import mysql.connector

from database.db import get_connection
from services.events import service as events  # activity log + notifications
from services.locking.service import lock_resource_then_booking
from models.checkin.model import EARLY_CHECKIN_MINUTES

VALID_DECISIONS = {"approve": "Approved", "reject": "Rejected"}
REQUIRED_FIELDS = ["resource_id", "start_time", "end_time", "purpose"]
MAX_PURPOSE_LENGTH = 255 
MAX_REASON_LENGTH = 255

# returns resource and requester details so the UI and admin queue show the correct names and contact info
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


from models.booking.cancel_in_use_block import BookingModelCancelInUseBlock  # noqa: E402
from models.booking.has_conflict_get import BookingModelHasConflictGet  # noqa: E402
from models.booking.decide_clean_decision import BookingModelDecideCleanDecision  # noqa: E402
from models.booking.create_parse_datetime import BookingModelCreateParseDatetime  # noqa: E402
from models.booking.validate_active_session_end import BookingModelValidateActiveSessionEnd  # noqa: E402


class BookingModel(BookingModelCancelInUseBlock, BookingModelHasConflictGet, BookingModelDecideCleanDecision, BookingModelCreateParseDatetime, BookingModelValidateActiveSessionEnd):
    @classmethod
    def _check_approvable(cls, conn, resource, current, booking_id):
        # checks again before approval because the resource or booking status may have changed while waiting
        if current["start_time"] < datetime.datetime.now():
            raise ValidationError("This booking has already started, so it can no longer be approved.")
        if not resource or resource["is_archived"]:
            raise ValidationError("This resource has been archived, so the booking cannot be approved.")
        if resource["status"] == "Maintenance":
            raise ValidationError("This resource is under Maintenance, so the booking cannot be approved.")
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

    @staticmethod
    def list_pending():
        # the admin review queue
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
        # requests already decided (Approved/Rejected), newest decision first
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
