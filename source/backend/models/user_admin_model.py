import re

import mysql.connector

from database.db import get_connection
from models.user_model import (
    ALL_ROLES,
    MAX_TEXT_LENGTH,
    UserModel,
    ValidationError,
    _check_password_rules,
    _clean_text,
    _clean_year,
)
from services import events

try:
    from services.timeutil import iso
except ImportError:  # copies of the project without services/timeutil.py
    def iso(value):
        return value.isoformat() if hasattr(value, "isoformat") else value


ROLE_LABEL = {
    "undergrad_student": "Undergraduate Student",
    "phd_student": "Ph.D. Student",
    "professor": "Professor",
    "admin": "Lab Administrator",
}
MAX_PROFILE_TEXT = 500  # professor_profiles.expertise / bio are VARCHAR(500)
MAX_TAG = 60  # one expertise topic
_EMAIL = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")
_STUDENT_ID = re.compile(r"\d{10}")


class NotFoundError(ValidationError):
    """The user id does not exist (the controller answers 404)."""


# field checks
def _email(value):
    value = value.strip().lower() if isinstance(value, str) else ""
    if not value:
        raise ValidationError("Email is required.")
    if len(value) > MAX_TEXT_LENGTH or not _EMAIL.match(value):
        raise ValidationError("Please enter a valid email address.")
    return value


def _role(value):
    if not isinstance(value, str) or value.strip() not in ALL_ROLES:
        raise ValidationError("Please choose a role.")
    return value.strip()


def _student_id(value):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str) or not _STUDENT_ID.fullmatch(value.strip()):
        raise ValidationError("Student ID must be exactly 10 digits.")
    return value.strip()


def _expertise(value):
# Databases, Security ,databases' -> 'Databases,Security' (the directory splits on commas)
    if value is None:
        return ""
    if isinstance(value, list):
        value = ",".join(str(v) for v in value)
    if not isinstance(value, str):
        raise ValidationError("Expertise must be text.")
    seen, tags = set(), []
    for tag in value.split(","):
        tag = " ".join(tag.split())
        if not tag or tag.lower() in seen:
            continue
        if len(tag) > MAX_TAG:
            raise ValidationError(f"Each expertise topic must be at most {MAX_TAG} characters.")
        seen.add(tag.lower())
        tags.append(tag)
    text = ",".join(tags)
    if len(text) > MAX_PROFILE_TEXT:
        raise ValidationError(f"Expertise must be at most {MAX_PROFILE_TEXT} characters in total.")
    return text


def _bio(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValidationError("Bio must be text.")
    value = " ".join(value.split())
    if len(value) > MAX_PROFILE_TEXT:
        raise ValidationError(f"Bio must be at most {MAX_PROFILE_TEXT} characters.")
    return value


def _lock_admins(cur):
# Lock every administrator row first, always in the same order, so two admins acting at the
# same moment are handled one after the other and cannot both pass the 'last admin' check
    cur.execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id FOR UPDATE")
    cur.fetchall()


def _other_active_admins(cur, user_id):
    cur.execute("SELECT COUNT(*) AS n FROM users WHERE role = 'admin' AND is_active = 1 AND id <> %s", (user_id,))
    return cur.fetchone()["n"]


_SELECT = """SELECT u.id, u.student_id, u.full_name, u.email, u.role, u.faculty, u.major, u.year,
                    u.is_active, u.email_verified, u.created_at,
                    (u.google_sub IS NOT NULL) AS google_linked,
                    COALESCE(p.expertise, '') AS expertise, COALESCE(p.bio, '') AS bio
             FROM users u LEFT JOIN professor_profiles p ON p.user_id = u.id"""


def serialize(row: dict) -> dict:
# What leaves the API: never the password hash or the Google subject id
    return {
        "id": row["id"],
        "student_id": row["student_id"],
        "full_name": row["full_name"] or "",
        "email": row["email"],
        "role": row["role"],
        "role_label": ROLE_LABEL.get(row["role"], row["role"]),
        "faculty": row["faculty"],
        "major": row["major"],
        "year": row["year"],
        "is_active": bool(row["is_active"]),
        "email_verified": bool(row["email_verified"]),
        "google_linked": bool(row["google_linked"]),
        "expertise": row["expertise"] if row["role"] == "professor" else "",
        "bio": row["bio"] if row["role"] == "professor" else "",
        "created_at": iso(row["created_at"]),
    }


class UserAdminModel:
    # list
    @staticmethod
    def list_users(query=None, role=None, status=None):
        if role not in (None, "") and role not in ALL_ROLES:
            raise ValidationError("Unknown role.")
        if status not in (None, "", "active", "inactive"):
            raise ValidationError("Status must be 'active' or 'inactive'.")
        sql, params, where = _SELECT, [], []
        if role:
            where.append("u.role = %s")
            params.append(role)
        if status:
            where.append("u.is_active = %s")
            params.append(1 if status == "active" else 0)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY u.is_active DESC, u.full_name, u.email"
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True, buffered=True)
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
        finally:
            conn.close()
        needle = " ".join(str(query or "").lower().split())
        if needle:
            rows = [r for r in rows if needle in " ".join(
                str(r[k] or "") for k in ("full_name", "email", "student_id", "faculty", "major")).lower()]
        return [serialize(r) for r in rows]

    @staticmethod
    def _get(cur, user_id):
        cur.execute(_SELECT + " WHERE u.id = %s", (user_id,))
        return cur.fetchone()

    # create
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
            # Created by an administrator: active, and the address needs no e-mailed link
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

    # edit (and role change)
    @classmethod
    def update(cls, admin_id: int, user_id: int, data: dict):
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True, buffered=True)
            _lock_admins(cur)
            cur.execute("SELECT * FROM users WHERE id = %s FOR UPDATE", (user_id,))
            old = cur.fetchone()
            if not old:
                raise NotFoundError("User not found.")
            cur.execute("SELECT expertise, bio FROM professor_profiles WHERE user_id = %s", (user_id,))
            profile = cur.fetchone()

            # A field that is not in the request keeps its current value
            def given(key, current):
                return data[key] if key in data else current

            full_name = _clean_text(given("full_name", old["full_name"]), "Full name", required=True)
            email = _email(given("email", old["email"]))
            role = _role(given("role", old["role"]))
            student_id = _student_id(given("student_id", old["student_id"])) \
                if role in ("undergrad_student", "phd_student") else None
            faculty = _clean_text(given("faculty", old["faculty"]), "Faculty")
            major = _clean_text(given("major", old["major"]), "Major")
            year = _clean_year(role, given("year", old["year"]))
            expertise = _expertise(given("expertise", profile["expertise"] if profile else "")) \
                if role == "professor" else None
            bio = _bio(given("bio", profile["bio"] if profile else "")) if role == "professor" else None

            role_changed = role != old["role"]
            if role_changed:
                if user_id == admin_id:
                    raise ValidationError("You cannot change your own role. Ask another administrator.")
                if old["role"] == "admin" and old["is_active"] and _other_active_admins(cur, user_id) == 0:
                    raise ValidationError("At least one active administrator must remain.")

            cur.execute("SELECT id FROM users WHERE email = %s AND id <> %s", (email, user_id))
            if cur.fetchone():
                raise ValidationError("Another account already uses this email.")
            if student_id:
                cur.execute("SELECT id FROM users WHERE student_id = %s AND id <> %s", (student_id, user_id))
                if cur.fetchone():
                    raise ValidationError("This Student ID is already registered to another account.")

            changed = [label for label, was, now in (
                ("name", old["full_name"], full_name), ("email", old["email"], email),
                ("student ID", old["student_id"], student_id), ("faculty", old["faculty"], faculty),
                ("major", old["major"], major), ("year", old["year"], year),
            ) if (was or None) != (now or None)]
            if role == "professor" and (
                    (profile["expertise"] if profile else "") != expertise or (profile["bio"] if profile else "") != bio):
                changed.append("professor profile")

            if not role_changed and not changed:
                return serialize(cls._get(cur, user_id)) # nothing to save, nothing to log

            # The Google identity belongs to the OLD address. If the e-mail changes, the link is
            # removed so that Google account can no longer open this account; the user signs in
            # with a password (forgot-password if none is set) or by Google with the new address.
            unlink_google = bool(old["google_sub"]) and email != old["email"]
            cur.execute(
                """UPDATE users SET student_id = %s, full_name = %s, email = %s, role = %s,
                          faculty = %s, major = %s, year = %s,
                          google_sub = CASE WHEN %s THEN NULL ELSE google_sub END WHERE id = %s""",
                (student_id, full_name, email, role, faculty, major, year, 1 if unlink_google else 0, user_id),
            )
            if role == "professor":
                if profile:
                    cur.execute("UPDATE professor_profiles SET expertise = %s, bio = %s WHERE user_id = %s",
                                (expertise, bio, user_id))
                else:
                    cur.execute("INSERT INTO professor_profiles (user_id, expertise, bio) VALUES (%s, %s, %s)",
                                (user_id, expertise, bio))
            who = f"{full_name} ({email})"
            if role_changed:
                events.user_event(conn, admin_id, "user.role_changed", user_id,
                                  f"{who}: {ROLE_LABEL[old['role']]} -> {ROLE_LABEL[role]}")
            if changed:
                note = " (Google link removed)" if unlink_google else ""
                events.user_event(conn, admin_id, "user.updated", user_id,
                                  f"{who}: changed {', '.join(changed)}{note}")
            conn.commit()
            return serialize(cls._get(cur, user_id))
        except mysql.connector.IntegrityError:
            conn.rollback()
            raise ValidationError("This Student ID or email is already registered.")
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # deactivate / reactivate
    @classmethod
    def set_active(cls, admin_id: int, user_id: int, active: bool):
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True, buffered=True)
            _lock_admins(cur)
            cur.execute("SELECT * FROM users WHERE id = %s FOR UPDATE", (user_id,))
            user = cur.fetchone()
            if not user:
                raise NotFoundError("User not found.")
            if bool(user["is_active"]) == active:
                raise ValidationError("This account is already active." if active
                                      else "This account is already deactivated.")
            if not active:
                if user_id == admin_id:
                    raise ValidationError("You cannot deactivate your own account.")
                if user["role"] == "admin" and _other_active_admins(cur, user_id) == 0:
                    raise ValidationError("At least one active administrator must remain.")
            cur.execute("UPDATE users SET is_active = %s WHERE id = %s", (1 if active else 0, user_id))
            events.user_event(
                conn, admin_id, "user.reactivated" if active else "user.deactivated", user_id,
                f"{user['full_name'] or user['email']} ({user['email']}), {ROLE_LABEL.get(user['role'], user['role'])}")
            conn.commit()
            return serialize(cls._get(cur, user_id))
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
