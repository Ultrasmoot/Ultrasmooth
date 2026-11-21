import datetime
import secrets
import models.user.model as _m

class UserModelVerifyEmailCreateResetToken:
    @classmethod
    def verify_email(cls, token: str):
        # consumes a verification token (single conditional UPDATE, so two
        # concurrent requests cannot both succeed) and marks the account verified
        if not isinstance(token, str) or not token or len(token) > 128:
            raise _m.ValidationError("This verification link is invalid or has expired.")
        token_hash = _m._hash_reset_token(token)

        conn = _m.get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "UPDATE email_verifications SET used = 1 "
                "WHERE token = %s AND used = 0 AND expires_at > %s",
                (token_hash, datetime.datetime.utcnow()),
            )
            if cur.rowcount != 1:
                conn.rollback()
                raise _m.ValidationError("This verification link is invalid or has expired.")
            cur.execute("SELECT user_id FROM email_verifications WHERE token = %s", (token_hash,))
            row = cur.fetchone()
            cur.execute("UPDATE users SET email_verified = 1 WHERE id = %s", (row["user_id"],))
            cur.execute(
                "UPDATE email_verifications SET used = 1 WHERE user_id = %s AND used = 0",
                (row["user_id"],),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # Forgot Password
    @classmethod
    def create_reset_token(cls, email: str):
        if not isinstance(email, str):
            return None
        user = cls.find_by_email(email.strip().lower())
        if not user or not user["is_active"]:
            return None

        token = secrets.token_urlsafe(32)
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(
            minutes=_m.Config.RESET_TOKEN_EXPIRES_MINUTES
        )
        conn = _m.get_connection()
        try:
            cur = conn.cursor()
            # Only the newest link works: older unused links for this user are retired.
            cur.execute(
                "UPDATE password_resets SET used = 1 WHERE user_id = %s AND used = 0",
                (user["id"],),
            )
            cur.execute(
                "INSERT INTO password_resets (user_id, token, expires_at) VALUES (%s, %s, %s)",
                (user["id"], _m._hash_reset_token(token), expires_at),
            )
            conn.commit()
        finally:
            conn.close()
        return token
