# account activation controls.
import models.user_admin.model as _m

class UserAdminModelSetActive:
    @classmethod
    def set_active(cls, admin_id: int, user_id: int, active: bool):
        conn = _m.get_connection()
        try:
            cur = conn.cursor(dictionary=True, buffered=True)
            _m._lock_admins(cur)
            cur.execute("SELECT * FROM users WHERE id = %s FOR UPDATE", (user_id,))
            user = cur.fetchone()
            if not user:
                raise _m.NotFoundError("User not found.")
            if bool(user["is_active"]) == active:
                raise _m.ValidationError("This account is already active." if active
                                      else "This account is already deactivated.")
            if not active:
                if user_id == admin_id:
                    raise _m.ValidationError("You cannot deactivate your own account.")
                if user["role"] == "admin" and _m._other_active_admins(cur, user_id) == 0:
                    raise _m.ValidationError("At least one active administrator must remain.")
            cur.execute("UPDATE users SET is_active = %s WHERE id = %s", (1 if active else 0, user_id))
            _m.events.user_event(
                conn, admin_id, "user.reactivated" if active else "user.deactivated", user_id,
                f"{user['full_name'] or user['email']} ({user['email']}), {_m.ROLE_LABEL.get(user['role'], user['role'])}")
            conn.commit()
            return _m.serialize(cls._get(cur, user_id))
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()