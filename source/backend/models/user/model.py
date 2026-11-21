import datetime
import hashlib
import re
import secrets

import bcrypt
import mysql.connector

from config import Config
from database.db import get_connection

# self-registration is limited to students. Professor and
# Admin accounts are created by an Admin only
STUDENT_ROLES = {"phd_student", "undergrad_student"}
ALL_ROLES = {"phd_student", "undergrad_student", "professor", "admin"}


# password / text validation rules
MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_LENGTH = 8
MAX_TEXT_LENGTH = 150 
MIN_YEAR, MAX_YEAR = 1, 6  # class year


class ValidationError(Exception):
    pass


from models.user.hash_reset_token_clean_text import _hash_reset_token, _clean_text, _clean_year
from models.user.check_password_rules_hash_password import _check_password_rules, UserModelCheckPasswordRulesHashPassword 
from models.user.authenticate_find_or_create_google_user import UserModelAuthenticateFindOrCreateGoogleUser 
from models.user.complete_google_signup_create_verificati import UserModelCompleteGoogleSignupCreateVerificati
from models.user.verify_email_create_reset_token import UserModelVerifyEmailCreateResetToken
from models.user.reset_password import UserModelResetPassword 


class UserModel(UserModelCheckPasswordRulesHashPassword, UserModelAuthenticateFindOrCreateGoogleUser, UserModelCompleteGoogleSignupCreateVerificati, UserModelVerifyEmailCreateResetToken, UserModelResetPassword):
    # email / password signup
    @classmethod
    def create_student_account(cls, data: dict):
        if not isinstance(data.get("role"), str):
            raise ValidationError(
                "Self sign-up is only available for Ph.D. and Undergraduate students."
            )
        role = data["role"].strip()
        if role not in STUDENT_ROLES:
            raise ValidationError(
                "Self sign-up is only available for Ph.D. and Undergraduate students."
            )

        student_id = data.get("student_id")
        student_id = student_id.strip() if isinstance(student_id, str) else ""
        if not re.fullmatch(r"\d{10}", student_id):
            raise ValidationError("Student ID must be exactly 10 digits.")

        full_name = _clean_text(data.get("full_name"), "Full name", required=True)
        faculty = _clean_text(data.get("faculty"), "Faculty")
        major = _clean_text(data.get("major"), "Major")
        year = _clean_year(role, data.get("year"))

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
                   (student_id, full_name, email, password_hash, role, faculty, major, year, email_verified)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0)""",
                (
                    student_id,
                    full_name,
                    email,
                    cls._hash_password(password),
                    role,
                    faculty,
                    major,
                    year,
                ),
            )
            conn.commit()
            return cls.find_by_id(cur.lastrowid)
        except mysql.connector.IntegrityError:
            conn.rollback()
            raise ValidationError("This Student ID or email is already registered.")
        finally:
            conn.close()
