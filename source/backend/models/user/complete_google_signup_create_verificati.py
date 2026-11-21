import datetime
import mysql.connector
import secrets
import models.user.model as _m

class UserModelCompleteGoogleSignupCreateVerificati:
    @classmethod
    def complete_google_signup(cls, google_sub: str, email: str, full_name: str, role: str, year=None):
        if not isinstance(role, str) or role not in _m.STUDENT_ROLES:
            raise _m.ValidationError("New Google sign-ups can only register with a student role.")
        year = _m._clean_year(role, year)  # undergrad must pick a class year
        conn = _m.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO users (full_name, email, google_sub, role, year)
                   VALUES (%s, %s, %s, %s, %s)""",
                ((full_name or "")[:_m.MAX_TEXT_LENGTH], (email or "").strip().lower(), google_sub, role, year),
            )
            conn.commit()
            return cls.find_by_id(cur.lastrowid)
        except mysql.connector.IntegrityError:
            conn.rollback()
            raise _m.ValidationError("An account with this email already exists.")
        finally:
            conn.close()

    # E-mail verification
    @classmethod
    def create_verification_token(cls, email: str):
        # creates a verification token for unverified accounts, stores only its hash, and invalidates older links
        if not isinstance(email, str):
            return None
        user = cls.find_by_email(email.strip().lower())
        if not user or not user["is_active"] or user.get("email_verified", 1):
            return None

        token = secrets.token_urlsafe(32)
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(
            minutes=_m.Config.VERIFY_TOKEN_EXPIRES_MINUTES
        )
        conn = _m.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE email_verifications SET used = 1 WHERE user_id = %s AND used = 0",
                (user["id"],),
            )
            cur.execute(
                "INSERT INTO email_verifications (user_id, token, expires_at) VALUES (%s, %s, %s)",
                (user["id"], _m._hash_reset_token(token), expires_at),
            )
            conn.commit()
        finally:
            conn.close()
        return token
