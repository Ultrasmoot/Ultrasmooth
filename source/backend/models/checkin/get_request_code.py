# get_request_code: part of models.checkin.model 
# the public names are still imported from models.checkin.model
import datetime
import math
import secrets
import models.checkin.model as _m

class CheckinModelGetRequestCode:
    @classmethod
    def get(cls, booking_id: int):
        conn = _m.get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(_m._SELECT + " WHERE b.id = %s", (booking_id,))
            return cur.fetchone()
        finally:
            conn.close()

    # 1. e-mail a code
    @classmethod
    def request_code(cls, booking_id: int, user: dict):
        now = _m._now()
        conn = _m.get_connection()
        try:
            cur, resource, booking = cls._lock(conn, booking_id, user["id"])
            reason = _m.block_reason(booking, resource["status"], now)
            if reason:
                raise _m.ValidationError(reason)

            cur.execute(
                "SELECT created_at FROM checkin_codes WHERE booking_id = %s ORDER BY id DESC LIMIT 1",
                (booking_id,),
            )
            last = cur.fetchone()
            if last:
                wait = _m.RESEND_COOLDOWN_SECONDS - (now - last["created_at"]).total_seconds()
                if wait > 0:
                    raise _m.CooldownError(math.ceil(wait))

            code = f"{secrets.randbelow(10 ** 6):06d}"
            # only the newest code works by retire any older unused ones.
            cur.execute(
                "UPDATE checkin_codes SET consumed_at = %s WHERE booking_id = %s AND consumed_at IS NULL",
                (now, booking_id),
            )
            cur.execute(
                """INSERT INTO checkin_codes (booking_id, user_id, code_hash, expires_at, created_at)
                   VALUES (%s, %s, %s, %s, %s)""",
                (booking_id, user["id"], _m._hash(booking_id, user["id"], code),
                 now + datetime.timedelta(seconds=_m.CODE_TTL_SECONDS), now),
            )
            code_id = cur.lastrowid
            conn.commit()
        except _m.ValidationError:
            conn.rollback()
            raise
        finally:
            conn.close()

        # send AFTER committing so the resource row is not locked while SMTP is slow.
        try:
            _m.mailer.send_checkin_code(user["email"], booking["resource_name"], code, _m.CODE_TTL_SECONDS // 60)
        except Exception:
            _m.logger.exception("Could not send the check-in code e-mail for booking %s", booking_id)
            # No e-mail went out, so the code must not exist (and must not count toward the resend cooldown).
            conn = _m.get_connection()
            try:
                conn.cursor().execute("DELETE FROM checkin_codes WHERE id = %s", (code_id,))
                conn.commit()
            finally:
                conn.close()
            raise _m.DeliveryError("Could not send the code e-mail. Please try again.")
        return {
            "email_hint": _m.mask_email(user["email"]),
            "expires_in": _m.CODE_TTL_SECONDS,
            "resend_in": _m.RESEND_COOLDOWN_SECONDS,
            "max_attempts": _m.MAX_ATTEMPTS,
        }
