# verify_code: part of models.checkin.model 
# the public names are still imported from models.checkin.model
import hmac
import re
import models.checkin.model as _m

class CheckinModelVerifyCode:
    # 2. verify the code 
    @classmethod
    def verify_code(cls, booking_id: int, raw_code, user: dict):
        code = re.sub(r"\s+", "", str(raw_code or ""))
        if not re.fullmatch(r"\d{6}", code):
            raise _m.ValidationError("Enter the 6-digit code.")
        now = _m._now()
        conn = _m.get_connection()
        try:
            cur, resource, booking = cls._lock(conn, booking_id, user["id"])
            # Everything is re-checked now, not only when the code was requested:
            # the resource may have gone into Maintenance while the e-mail was on its way.
            reason = _m.block_reason(booking, resource["status"], now)
            if reason:
                raise _m.ValidationError(reason)

            cur.execute(
                """SELECT * FROM checkin_codes
                   WHERE booking_id = %s AND user_id = %s AND consumed_at IS NULL
                   ORDER BY id DESC LIMIT 1 FOR UPDATE""",
                (booking_id, user["id"]),
            )
            row = cur.fetchone()
            if not row:
                raise _m.ValidationError("No active code. Please request a new code.")
            if now > row["expires_at"]:
                raise _m.ValidationError("This code has expired. Please request a new one.")
            if row["attempts"] >= _m.MAX_ATTEMPTS:
                raise _m.WrongCodeError("Too many incorrect attempts. Please request a new code.", 0)

            if not hmac.compare_digest(row["code_hash"], _m._hash(booking_id, user["id"], code)):
                attempts = row["attempts"] + 1
                cur.execute("UPDATE checkin_codes SET attempts = %s WHERE id = %s", (attempts, row["id"]))
                left = _m.MAX_ATTEMPTS - attempts
                _m.events.checkin_code_failed(conn, booking_id, left)   # Iteration 5: logged with the counter
                conn.commit()  # the failed guess must be counted even though the request fails
                if left > 0:
                    raise _m.WrongCodeError(f"Incorrect code. {left} attempt{'s' if left != 1 else ''} left.", left)
                raise _m.WrongCodeError("Incorrect code. Too many attempts — please request a new code.", 0)

            cur.execute("UPDATE checkin_codes SET consumed_at = %s WHERE id = %s", (now, row["id"]))
            cur.execute("UPDATE bookings SET checked_in_at = %s WHERE id = %s", (now, booking_id))
            cur.execute("UPDATE resources SET status = 'In Use' WHERE id = %s", (resource["id"],))
            _m.events.checkin_done(conn, booking_id)
            conn.commit()
        except _m.ValidationError:
            conn.rollback()
            raise
        finally:
            conn.close()
        return cls.get(booking_id)
