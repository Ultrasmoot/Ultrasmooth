import re
import bcrypt
import mysql.connector

from config import Config
from database.db import get_connection

# SRS-11 / URS-9: self-registration is limited to students. Professor and
# Admin accounts are created by an Admin only (SRS-13, Iteration 6).
STUDENT_ROLES = {"phd_student", "undergrad_student"}
ALL_ROLES = {"phd_student", "undergrad_student", "professor", "admin"}

class ValidationError(Exception):
    pass

class UserModel:
    # password helpers
    @staticmethod
    def _hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    # check password
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
        role = (data.get("role") or "").strip()
        if role not in STUDENT_ROLES:
            raise ValidationError("Self sign-up is only available for Ph.D. and Undergraduate students.")

        student_id = (data.get("student_id") or "").strip()
        if not re.fullmatch(r"\d{10}", student_id):
            raise ValidationError("Student ID must be exactly 10 digits.")

        full_name = (data.get("full_name") or "").strip()
        if not full_name:
            raise ValidationError("Full name is required.")

        email = (data.get("email") or "").strip().lower()
        if "@" not in email:
            raise ValidationError("Please enter a valid email address.")

        allowed_domain = Config.ALLOWED_EMAIL_DOMAIN
        if allowed_domain and not email.endswith("@" + allowed_domain):
            raise ValidationError(f"Sign-up is only available for @{allowed_domain} email addresses.")

        password = data.get("password") or ""
        if len(password) < 8:
            raise ValidationError("Password must be at least 8 characters.")

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
                    data.get("faculty"),
                    data.get("major"),
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
                "UPDATE users SET google_sub = %s WHERE id = %s"
                (google_sub, user["id"]),
            )
            conn.commit()
        finally:
            conn.close()
        return cls.find_by_id(user["id"]), False

    return None, True
