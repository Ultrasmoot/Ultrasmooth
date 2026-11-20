# Check in / check out (US-10, SRS-10)
# A student checks in to one of their own Approved bookings by confirming a
# 6-digit code that is e-mailed to the address they registered with. A valid
# code sets the resource to "In Use"; check-out sets it back to "Available".
import datetime
import hashlib
import hmac
import logging
import math
import re
import secrets

from config import Config
from database.db import get_connection
from services.events import service as events  # activity log
from services.mailer import service as mailer
from services.locking.service import lock_resource_then_booking  

logger = logging.getLogger(__name__)

EARLY_CHECKIN_MINUTES = 15   # check-in opens this long before the booking starts
CODE_TTL_SECONDS = 300       # a code is valid for 5 minutes
MAX_ATTEMPTS = 3             # wrong guesses allowed per code
RESEND_COOLDOWN_SECONDS = 30  # minimum gap between two codes for the same booking
DONE_HISTORY_DAYS = 30
DONE_LIMIT = 10


class ValidationError(Exception):
    pass


class WrongCodeError(ValidationError):
    def __init__(self, message, attempts_left):
        super().__init__(message)
        self.attempts_left = attempts_left


class CooldownError(ValidationError):
    def __init__(self, retry_after):
        super().__init__(f"Please wait {retry_after}s before requesting another code.")
        self.retry_after = retry_after


class DeliveryError(Exception):
    """The code e-mail could not be sent."""


_SELECT = """
    SELECT b.*, r.name AS resource_name, r.resource_code AS resource_code,
           r.status AS resource_status
    FROM bookings b JOIN resources r ON r.id = b.resource_id
"""


from models.checkin.list_mine_lock import CheckinModelListMineLock  # noqa: E402
from models.checkin.get_request_code import CheckinModelGetRequestCode  # noqa: E402
from models.checkin.verify_code import CheckinModelVerifyCode  # noqa: E402
from models.checkin.check_out import CheckinModelCheckOut  # noqa: E402


class CheckinModel(CheckinModelListMineLock, CheckinModelGetRequestCode, CheckinModelVerifyCode, CheckinModelCheckOut):
    pass


def _now():
    # Same convention as BookingModel: booking times are naive server-local
    # datetimes, so "now" is naive server-local too. Tests patch this function.
    return datetime.datetime.now()


def _hash(booking_id: int, user_id: int, code: str) -> str:
    # HMAC with the server secret, bound to this booking and user. (A 6-digit
    # code is guessable if the DB leaks; the real protection is the short expiry,
    # the 3-attempt limit and single use.)
    msg = f"{booking_id}:{user_id}:{code}".encode()
    return hmac.new(Config.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()


def mask_email(email: str) -> str:
    name, _, domain = str(email).partition("@")
    return f"{name[:1]}*****@{domain}" if domain else "*****"


def _fmt_open_time(opens_at: datetime.datetime, now: datetime.datetime) -> str:
    if opens_at.date() == now.date():
        return f"Check-in opens at {opens_at:%H:%M}."
    return f"Check-in opens on {opens_at:%d %b} at {opens_at:%H:%M}."


def block_reason(booking: dict, resource_status: str, now: datetime.datetime):
    """Why this booking cannot be checked in to right now (None = it can)."""
    if booking["status"] != "Approved":
        return "This booking is not approved."
    if booking["checked_in_at"]:
        return "You have already checked in."
    if resource_status == "Maintenance":
        return "This resource is under maintenance."
    if resource_status == "In Use":
        return "This resource is currently in use by someone else."
    opens_at = booking["start_time"] - datetime.timedelta(minutes=EARLY_CHECKIN_MINUTES)
    if now < opens_at:
        return _fmt_open_time(opens_at, now)
    if now > booking["end_time"]:
        return "Your booking has ended."
    return None
