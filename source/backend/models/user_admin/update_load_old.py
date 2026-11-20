# user update operations
import mysql.connector
import models.user_admin.model as _m

class UserAdminModelUpdateLoadOld:
    @classmethod
    def update(cls, admin_id: int, user_id: int, data: dict):
        conn = _m.get_connection()
        try:
            cur = conn.cursor(dictionary=True, buffered=True)
            _m._lock_admins(cur)
            old, profile = cls._load_old(cur, user_id)
            f = cls._collect_fields(data, old, profile)
            role_changed = f["role"] != old["role"]
            if role_changed:
                cls._check_role_change(cur, admin_id, user_id, old)
            cls._check_unique(cur, user_id, f["email"], f["student_id"])
            changed = cls._changed_labels(old, profile, f)
            if not role_changed and not changed:
                return _m.serialize(cls._get(cur, user_id))
            # remove the Google link when the email changes
            unlink_google = bool(old["google_sub"]) and f["email"] != old["email"]
            cls._write_user(cur, user_id, f, profile, unlink_google)
            cls._log_update(conn, admin_id, user_id, (old, f), role_changed, changed, unlink_google)
            conn.commit()
            return _m.serialize(cls._get(cur, user_id))
        except mysql.connector.IntegrityError:
            conn.rollback()
            raise _m.ValidationError("This Student ID or email is already registered.")
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _load_old(cur, user_id):
        cur.execute("SELECT * FROM users WHERE id = %s FOR UPDATE", (user_id,))
        old = cur.fetchone()
        if not old:
            raise _m.NotFoundError("User not found.")
        cur.execute("SELECT expertise, bio FROM professor_profiles WHERE user_id = %s", (user_id,))
        return old, cur.fetchone()

    @staticmethod
    def _collect_fields(data: dict, old: dict, profile) -> dict:
        # keep current values for omitted fields
        def given(key, current):
            return data[key] if key in data else current

        role = _m._role(given("role", old["role"]))
        is_professor = role == "professor"
        student = role in ("undergrad_student", "phd_student")
        return {
            "full_name": _m._clean_text(given("full_name", old["full_name"]), "Full name", required=True),
            "email": _m._email(given("email", old["email"])),
            "role": role,
            "student_id": _m._student_id(given("student_id", old["student_id"])) if student else None,
            "faculty": _m._clean_text(given("faculty", old["faculty"]), "Faculty"),
            "major": _m._clean_text(given("major", old["major"]), "Major"),
            "year": _m._clean_year(role, given("year", old["year"])),
            "expertise": _m._expertise(given("expertise", profile["expertise"] if profile else ""))
            if is_professor else None,
            "bio": _m._bio(given("bio", profile["bio"] if profile else "")) if is_professor else None,
        }