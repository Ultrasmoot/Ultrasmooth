# user listing methods
import models.user_admin.model as _m

class UserAdminModelListUsersGet:
    @staticmethod
    def list_users(query=None, role=None, status=None):
        if role not in (None, "") and role not in _m.ALL_ROLES:
            raise _m.ValidationError("Unknown role.")
        if status not in (None, "", "active", "inactive"):
            raise _m.ValidationError("Status must be 'active' or 'inactive'.")
        sql, params, where = _m._SELECT, [], []
        if role:
            where.append("u.role = %s")
            params.append(role)
        if status:
            where.append("u.is_active = %s")
            params.append(1 if status == "active" else 0)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY u.is_active DESC, u.full_name, u.email"
        conn = _m.get_connection()
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
        return [_m.serialize(r) for r in rows]

    @staticmethod
    def _get(cur, user_id):
        cur.execute(_m._SELECT + " WHERE u.id = %s", (user_id,))
        return cur.fetchone()