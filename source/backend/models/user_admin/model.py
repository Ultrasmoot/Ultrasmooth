# user management and account controls
# admins can manage users but cannot remove the last active admin
import re

import mysql.connector

from database.db import get_connection
from models.user.model import (
    ALL_ROLES,
    MAX_TEXT_LENGTH,
    UserModel,
    ValidationError,
    _check_password_rules,
    _clean_text,
    _clean_year,
)
from services.events import service as events


ROLE_LABEL = {
    "undergrad_student": "Undergraduate Student",
    "phd_student": "Ph.D. Student",
    "professor": "Professor",
    "admin": "Lab Administrator",
}
MAX_PROFILE_TEXT = 500  
MAX_TAG = 60                     
_EMAIL = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")
_STUDENT_ID = re.compile(r"\d{10}")


class NotFoundError(ValidationError):
    """Raised when a user ID does not exist."""


_SELECT = """SELECT u.id, u.student_id, u.full_name, u.email, u.role, u.faculty, u.major, u.year,
                    u.is_active, u.email_verified, u.created_at,
                    (u.google_sub IS NOT NULL) AS google_linked,
                    COALESCE(p.expertise, '') AS expertise, COALESCE(p.bio, '') AS bio
             FROM users u LEFT JOIN professor_profiles p ON p.user_id = u.id"""


from models.user_admin.list_users_get import UserAdminModelListUsersGet  # noqa: E402
from models.user_admin.set_active import UserAdminModelSetActive  # noqa: E402
from models.user_admin.update_load_old import UserAdminModelUpdateLoadOld  # noqa: E402
from models.user_admin.check_role_change_check_unique import UserAdminModelCheckRoleChangeCheckUnique  # noqa: E402
from models.user_admin.log_update_iso import iso, _email, _role, _student_id, UserAdminModelLogUpdateIso  # noqa: E402
from models.user_admin.expertise_bio import _expertise, _bio, _lock_admins, _other_active_admins, serialize  # noqa: E402


class UserAdminModel(UserAdminModelListUsersGet, UserAdminModelSetActive, UserAdminModelUpdateLoadOld, UserAdminModelCheckRoleChangeCheckUnique, UserAdminModelLogUpdateIso):
    @classmethod
    def create(cls, admin_id: int, data: dict):
        full_name = _clean_text(data.get("full_name"), "Full name", required=True)
        email = _email(data.get("email"))
        role = _role(data.get("role"))
        student_id = _student_id(data.get("student_id")) if role in ("undergrad_student", "phd_student") else None
        faculty = _clean_text(data.get("faculty"), "Faculty")
        major = _clean_text(data.get("major"), "Major")
        year = _clean_year(role, data.get("year"))
        password = data.get("password")
        _check_password_rules(password)
        expertise = _expertise(data.get("expertise")) if role == "professor" else ""
        bio = _bio(data.get("bio")) if role == "professor" else ""

        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True, buffered=True)
            cur.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cur.fetchone():
                raise ValidationError("An account with this email already exists.")
            if student_id:
                cur.execute("SELECT id FROM users WHERE student_id = %s", (student_id,))
                if cur.fetchone():
                    raise ValidationError("This Student ID is already registered.")
            # admin created accounts are active and already verified
            cur.execute(
                """INSERT INTO users
                   (student_id, full_name, email, password_hash, role, faculty, major, year, is_active, email_verified)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, 1)""",
                (student_id, full_name, email, UserModel._hash_password(password), role, faculty, major, year),
            )
            new_id = cur.lastrowid
            if role == "professor":
                cur.execute("INSERT INTO professor_profiles (user_id, expertise, bio) VALUES (%s, %s, %s)",
                            (new_id, expertise, bio))
            events.user_event(conn, admin_id, "user.created", new_id,
                              f"{full_name} ({email}) as {ROLE_LABEL[role]}")
            conn.commit()
            return serialize(cls._get(cur, new_id))
        except mysql.connector.IntegrityError:
            conn.rollback()
            raise ValidationError("This Student ID or email is already registered.")
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()