import datetime
import re
import secrets

import bcrypt
import mysql.connector

from config import Config
from database.db import get_connection

# SRS-11 / URS-9: self-registration is limited to students. Professor and
# Admin accounts are created by an Admin only (SRS-13, Iteration 6).
STUDENT_ROLES = {"phd_student", "undergrad_student"}
ALL_ROLES = {"phd_student", "undergrad_student", "professor", "admin"}

# password and text validation rules
# limit bcrypt to only uses the first 72 bytes of a password
MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_LENGTH = 8
MAX_TEXT_LENGTH = 150  # matches VARCHAR(150) columns


class ValidationError(Exception):
    pass


def _clean_text(value, field: str, required: bool = False):
#return a stripped string, rejecting non-string, too long input
    if value is None or value == "":
        if required:
            raise ValidationError(f"{field} is required.")
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be text.")
    value = value.strip()
    if required and not value:
        raise ValidationError(f"{field} is required.")
    if len(value) > MAX_TEXT_LENGTH:
        raise ValidationError(f"{field} must be at most {MAX_TEXT_LENGTH} characters.")
    return value or None


def _check_password_rules(password):
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValidationError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes long.")


class UserModel:
    # password helpers
    # hash password
    @staticmethod
    def _hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    # Napakhet - check password
    @staticmethod
    def _check_password(password: str, password_hash: str) -> bool:
        if not password_hash:
            return False
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))

    # lookups
    @staticmethod
    def find_by_email(email: str):
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM users WHERE email = %s", (email,))
            return cur.fetchone()
        finally:
            conn.close()

    @staticmethod
    def find_by_google_sub(sub: str):
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM users WHERE google_sub = %s", (sub,))
            return cur.fetchone()
        finally:
            conn.close()

    # section that use in middleware
    @staticmethod
    def find_by_id(user_id: int):
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            return cur.fetchone()
        finally:
            conn.close()

    # email-password login (US-11)
    @classmethod
    def create_student_account(cls, data: dict):
        if not isinstance(data.get("role"), str):
            raise ValidationError("Self sign-up is only available for Ph.D. and Undergraduate students.")
        role = data["role"].strip()
        if role not in STUDENT_ROLES:
            raise ValidationError("Self sign-up is only available for Ph.D. and Undergraduate students.")

        student_id = data.get("student_id")
        student_id = student_id.strip() if isinstance(student_id, str) else ""
        if not re.fullmatch(r"\d{10}", student_id):
            raise ValidationError("Student ID must be exactly 10 digits.")

        full_name = _clean_text(data.get("full_name"), "Full name", required=True)
        faculty = _clean_text(data.get("faculty"), "Faculty")
        major = _clean_text(data.get("major"), "Major")

        email = data.get("email")
        email = email.strip().lower() if isinstance(email, str) else ""
        if "@" not in email or len(email) > MAX_TEXT_LENGTH:
            raise ValidationError("Please enter a valid email address.")

        allowed_domain = Config.ALLOWED_EMAIL_DOMAIN
        if allowed_domain and not email.endswith("@" + allowed_domain):
            raise ValidationError(f"Sign-up is only available for @{allowed_domain} email addresses.")

        password = data.get("password")
        _check_password_rules(password)

        if cls.find_by_email(email):
            raise ValidationError("An account with this email already exists.")

        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO users
                   (student_id, full_name, email, password_hash, role, faculty, major)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    student_id,
                    full_name,
                    email,
                    cls._hash_password(password),
                    role,
                    faculty,
                    major,
                ),
            )
            conn.commit()
            return cls.find_by_id(cur.lastrowid)
        except mysql.connector.IntegrityError:
            conn.rollback()
            raise ValidationError("This Student ID or email is already registered.")
        finally:
            conn.close()

    # email login (US-11)
    @classmethod
    def authenticate(cls, email: str, password: str):
        user = cls.find_by_email((email or "").strip().lower())
        if not user or not user["is_active"]:
            return None
        if not cls._check_password(password, user["password_hash"]):
            return None
        return user

    # Google login (US-11)
    @classmethod
    def find_or_create_google_user(cls, google_sub: str, email: str, full_name: str):
        # find existing Google user or return a new user.
        user = cls.find_by_google_sub(google_sub)
        if user:
            return user, False

        user = cls.find_by_email(email)
        if user:
            conn = get_connection()
            try:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE users SET google_sub = %s WHERE id = %s",
                    (google_sub, user["id"]),
                )
                conn.commit()
            finally:
                conn.close()
            return cls.find_by_id(user["id"]), False

        return None, True

    @classmethod
    def complete_google_signup(cls, google_sub: str, email: str, full_name: str, role: str):
        if role not in STUDENT_ROLES:
            raise ValidationError("New Google sign-ups can only register with a student role.")
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO users (full_name, email, google_sub, role)
                   VALUES (%s, %s, %s, %s)""",
                ((full_name or "")[:MAX_TEXT_LENGTH], (email or "").strip().lower(), google_sub, role),
            )
            conn.commit()
            return cls.find_by_id(cur.lastrowid)
        except mysql.connector.IntegrityError:
            conn.rollback()
            raise ValidationError("An account with this email already exists.")
        finally:
            conn.close()

    # forgot password
    @classmethod
    def create_reset_token(cls, email: str):
        """Returns a reset token if the email matches an active account,
        else None. Callers must not reveal which case occurred — always
        respond the same way either way, to avoid confirming which emails
        have accounts."""
        user = cls.find_by_email((email or "").strip().lower())
        if not user or not user["is_active"]:
            return None

        token = secrets.token_urlsafe(32)
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(
            minutes=Config.RESET_TOKEN_EXPIRES_MINUTES
        )
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO password_resets (user_id, token, expires_at) VALUES (%s, %s, %s)",
                (user["id"], token, expires_at),
            )
            conn.commit()
        finally:
            conn.close()
        return token

    @staticmethod
    def _find_valid_reset(token: str):
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT * FROM password_resets WHERE token = %s AND used = 0 AND expires_at > %s",
                (token, datetime.datetime.utcnow()),
            )
            return cur.fetchone()
        finally:
            conn.close()

    # reset password (single-use token)
    @classmethod
    def reset_password(cls, token: str, new_password: str):
        # check the reset token and update the password
        if not isinstance(token, str) or not token or len(token) > 128:
            raise ValidationError("This reset link is invalid or has expired.")
        # validate the password first
        _check_password_rules(new_password)

        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "UPDATE password_resets SET used = 1 "
                "WHERE token = %s AND used = 0 AND expires_at > %s",
                (token, datetime.datetime.utcnow()),
            )
            if cur.rowcount != 1:
                conn.rollback()
                raise ValidationError("This reset link is invalid or has expired.")
            cur.execute("SELECT user_id FROM password_resets WHERE token = %s", (token,))
            row = cur.fetchone()
            cur.execute(
                "UPDATE users SET password_hash = %s WHERE id = %s",
                (cls._hash_password(new_password), row["user_id"]),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()