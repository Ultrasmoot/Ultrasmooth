# user role and profile validation
import models.user_admin.model as _m

class UserAdminModelCheckRoleChangeCheckUnique:
    @staticmethod
    def _check_role_change(cur, admin_id, user_id, old):
        if user_id == admin_id:
            raise _m.ValidationError("You cannot change your own role. Ask another administrator.")
        if old["role"] == "admin" and old["is_active"] and _m._other_active_admins(cur, user_id) == 0:
            raise _m.ValidationError("At least one active administrator must remain.")

    @staticmethod
    def _check_unique(cur, user_id, email, student_id):
        cur.execute("SELECT id FROM users WHERE email = %s AND id <> %s", (email, user_id))
        if cur.fetchone():
            raise _m.ValidationError("Another account already uses this email.")
        if student_id:
            cur.execute("SELECT id FROM users WHERE student_id = %s AND id <> %s", (student_id, user_id))
            if cur.fetchone():
                raise _m.ValidationError("This Student ID is already registered to another account.")

    @staticmethod
    def _changed_labels(old, profile, f) -> list:
        changed = [label for label, was, now in (
            ("name", old["full_name"], f["full_name"]), ("email", old["email"], f["email"]),
            ("student ID", old["student_id"], f["student_id"]), ("faculty", old["faculty"], f["faculty"]),
            ("major", old["major"], f["major"]), ("year", old["year"], f["year"]),
        ) if (was or None) != (now or None)]
        if f["role"] == "professor" and (
                (profile["expertise"] if profile else "") != f["expertise"]
                or (profile["bio"] if profile else "") != f["bio"]):
            changed.append("professor profile")
        return changed

    @staticmethod
    def _write_user(cur, user_id, f, profile, unlink_google):
        cur.execute(
            """UPDATE users SET student_id = %s, full_name = %s, email = %s, role = %s,
                      faculty = %s, major = %s, year = %s,
                      google_sub = CASE WHEN %s THEN NULL ELSE google_sub END WHERE id = %s""",
            (f["student_id"], f["full_name"], f["email"], f["role"], f["faculty"], f["major"], f["year"],
             1 if unlink_google else 0, user_id),
        )
        if f["role"] != "professor":
            return
        if profile:
            cur.execute("UPDATE professor_profiles SET expertise = %s, bio = %s WHERE user_id = %s",
                        (f["expertise"], f["bio"], user_id))
        else:
            cur.execute("INSERT INTO professor_profiles (user_id, expertise, bio) VALUES (%s, %s, %s)",
                        (user_id, f["expertise"], f["bio"]))