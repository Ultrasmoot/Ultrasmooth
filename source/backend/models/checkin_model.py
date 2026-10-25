# approve check-in by sent code to email (feel like otp)
import datetime
import hashlib
import hmac
import math
import re
import secrets

from config import Config
from database.db import get_connection
from services import mailer

EARLY_CHECKIN_MINUTES = 15 
CODE_TTL_SECONDS = 300
MAX_ATTEMPTS = 3
RESEND_COOLDOWN_SECONDS = 30 
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


def _now():
    # Same convention as BookingModel: booking times are naive server-local
    # datetimes, so "now" is naive server-local too. Tests patch this function.
    return datetime.datetime.now()


def _hash(booking_id: int, user_id: int, code: str) -> str:
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


_SELECT = """
    SELECT b.*, r.name AS resource_name, r.resource_code AS resource_code,
           r.status AS resource_status
    FROM bookings b JOIN resources r ON r.id = b.resource_id
"""


class CheckinModel:
    # list
    @staticmethod
    def list_mine(user_id: int):
        now = _now()
        since = now - datetime.timedelta(days=DONE_HISTORY_DAYS)
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                _SELECT + """ WHERE b.requester_id = %s AND b.status = 'Approved'
                              AND b.end_time >= %s ORDER BY b.start_time ASC""",
                (user_id, since),
            )
            rows = cur.fetchall()
        finally:
            conn.close()

        in_use, ready, done = [], [], []
        for b in rows:
            if b["checked_in_at"] and not b["checked_out_at"]:
                in_use.append(b)
            elif b["checked_out_at"]:
                done.append(b)
            elif b["end_time"] > now:
                b["block_reason"] = block_reason(b, b["resource_status"], now)
                ready.append(b)
        done.sort(key=lambda b: b["checked_out_at"], reverse=True)
        return {"in_use": in_use, "ready": ready, "done": done[:DONE_LIMIT]}

    # internal
    @staticmethod
    def _lock(conn, booking_id: int, user_id: int):
        """Lock the resource row, then the booking row (locking reads, so the
        latest committed state is seen), and make sure the booking is the caller's.
        Same lock order as everywhere else: resource first."""
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT resource_id FROM bookings WHERE id = %s", (booking_id,))
        row = cur.fetchone()
        if not row:
            raise ValidationError("Booking not found.")
        cur.execute("SELECT id, status FROM resources WHERE id = %s FOR UPDATE", (row["resource_id"],))
        resource = cur.fetchone()
        cur.execute(_SELECT + " WHERE b.id = %s FOR UPDATE", (booking_id,))
        booking = cur.fetchone()
        # Someone else's booking looks exactly like a missing one.
        if not booking or booking["requester_id"] != user_id:
            raise ValidationError("Booking not found.")
        return cur, resource, booking

    @classmethod
    def get(cls, booking_id: int):
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(_SELECT + " WHERE b.id = %s", (booking_id,))
            return cur.fetchone()
        finally:
            conn.close()

    # e-mail a code
    @classmethod
    def request_code(cls, booking_id: int, user: dict):
        now = _now()
        conn = get_connection()
        try:
            cur, resource, booking = cls._lock(conn, booking_id, user["id"])
            reason = block_reason(booking, resource["status"], now)
            if reason:
                raise ValidationError(reason)

            cur.execute(
                "SELECT created_at FROM checkin_codes WHERE booking_id = %s ORDER BY id DESC LIMIT 1",
                (booking_id,),
            )
            last = cur.fetchone()
            if last:
                wait = RESEND_COOLDOWN_SECONDS - (now - last["created_at"]).total_seconds()
                if wait > 0:
                    raise CooldownError(math.ceil(wait))

            code = f"{secrets.randbelow(10 ** 6):06d}"
            # Only the newest code works: retire any older unused ones.
            cur.execute(
                "UPDATE checkin_codes SET consumed_at = %s WHERE booking_id = %s AND consumed_at IS NULL",
                (now, booking_id),
            )
            cur.execute(
                """INSERT INTO checkin_codes (booking_id, user_id, code_hash, expires_at, created_at)
                   VALUES (%s, %s, %s, %s, %s)""",
                (booking_id, user["id"], _hash(booking_id, user["id"], code),
                 now + datetime.timedelta(seconds=CODE_TTL_SECONDS), now),
            )
            code_id = cur.lastrowid
            conn.commit()
        except ValidationError:
            conn.rollback()
            raise
        finally:
            conn.close()

        # Send AFTER committing so the resource row is not locked while SMTP is slow.
        try:
            mailer.send_checkin_code(user["email"], booking["resource_name"], code, CODE_TTL_SECONDS // 60)
        except Exception:
            # No e-mail went out, so the code must not exist (and must not count toward the resend cooldown)
            conn = get_connection()
            try:
                conn.cursor().execute("DELETE FROM checkin_codes WHERE id = %s", (code_id,))
                conn.commit()
            finally:
                conn.close()
            raise DeliveryError("Could not send the code e-mail. Please try again.")
        return {
            "email_hint": mask_email(user["email"]),
            "expires_in": CODE_TTL_SECONDS,
            "resend_in": RESEND_COOLDOWN_SECONDS,
            "max_attempts": MAX_ATTEMPTS,
        }

    # verify the code
    @classmethod
    def verify_code(cls, booking_id: int, raw_code, user: dict):
        code = re.sub(r"\s+", "", str(raw_code or ""))
        if not re.fullmatch(r"\d{6}", code):
            raise ValidationError("Enter the 6-digit code.")
        now = _now()
        conn = get_connection()
        try:
            cur, resource, booking = cls._lock(conn, booking_id, user["id"])
            # Everything is re-checked now, not only when the code was requested:
            # the resource may have gone into Maintenance while the e-mail was on its way.
            reason = block_reason(booking, resource["status"], now)
            if reason:
                raise ValidationError(reason)

            cur.execute(
                """SELECT * FROM checkin_codes
                   WHERE booking_id = %s AND user_id = %s AND consumed_at IS NULL
                   ORDER BY id DESC LIMIT 1 FOR UPDATE""",
                (booking_id, user["id"]),
            )
            row = cur.fetchone()
            if not row:
                raise ValidationError("No active code. Please request a new code.")
            if now > row["expires_at"]:
                raise ValidationError("This code has expired. Please request a new one.")
            if row["attempts"] >= MAX_ATTEMPTS:
                raise WrongCodeError("Too many incorrect attempts. Please request a new code.", 0)

            if not hmac.compare_digest(row["code_hash"], _hash(booking_id, user["id"], code)):
                attempts = row["attempts"] + 1
                cur.execute("UPDATE checkin_codes SET attempts = %s WHERE id = %s", (attempts, row["id"]))
                conn.commit()  # the failed guess must be counted even though the request fails
                left = MAX_ATTEMPTS - attempts
                if left > 0:
                    raise WrongCodeError(f"Incorrect code. {left} attempt{'s' if left != 1 else ''} left.", left)
                raise WrongCodeError("Incorrect code. Too many attempts — please request a new code.", 0)

            cur.execute("UPDATE checkin_codes SET consumed_at = %s WHERE id = %s", (now, row["id"]))
            cur.execute("UPDATE bookings SET checked_in_at = %s WHERE id = %s", (now, booking_id))
            cur.execute("UPDATE resources SET status = 'In Use' WHERE id = %s", (resource["id"],))
            conn.commit()
        except ValidationError:
            conn.rollback()
            raise
        finally:
            conn.close()
        return cls.get(booking_id)

    # check out
    @classmethod
    def check_out(cls, booking_id: int, user: dict):
        now = _now()
        conn = get_connection()
        try:
            cur, resource, booking = cls._lock(conn, booking_id, user["id"])
            if not booking["checked_in_at"]:
                raise ValidationError("You have not checked in to this booking.")
            if booking["checked_out_at"]:
                raise ValidationError("You have already checked out.")
            cur.execute("UPDATE bookings SET checked_out_at = %s WHERE id = %s", (now, booking_id))
            # Free the resource only if it is still "In Use". If an admin has moved it to Maintenance
            # the time is recorded but the resource must stay blocked.
            if resource["status"] == "In Use":
                cur.execute("UPDATE resources SET status = 'Available' WHERE id = %s", (resource["id"],))
            conn.commit()
        except ValidationError:
            conn.rollback()
            raise
        finally:
            conn.close()
        return cls.get(booking_id)
