import datetime
import models.user.model as _m

class UserModelResetPassword:
    # reset password (single-use token)
    @classmethod
    def reset_password(cls, token: str, new_password: str):
        """Validates a reset token, updates the password, and marks the
        token used in ONE transaction. The token is consumed with a single
        conditional UPDATE, so two concurrent requests cannot both succeed
        (single-use, time-limited)."""
        if not isinstance(token, str) or not token or len(token) > 128:
            raise _m.ValidationError("This reset link is invalid or has expired.")
        # Validate the password first so a typo doesn't burn the token.
        _m._check_password_rules(new_password)
        token_hash = _m._hash_reset_token(token)

        conn = _m.get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "UPDATE password_resets SET used = 1 "
                "WHERE token = %s AND used = 0 AND expires_at > %s",
                (token_hash, datetime.datetime.utcnow()),
            )
            if cur.rowcount != 1:
                conn.rollback()
                raise _m.ValidationError("This reset link is invalid or has expired.")
            cur.execute("SELECT user_id FROM password_resets WHERE token = %s", (token_hash,))
            row = cur.fetchone()
            cur.execute(
                "UPDATE users SET password_hash = %s WHERE id = %s",
                (cls._hash_password(new_password), row["user_id"]),
            )
            # Any other reset link still outstanding for this user dies with this one.
            cur.execute(
                "UPDATE password_resets SET used = 1 WHERE user_id = %s AND used = 0",
                (row["user_id"],),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
