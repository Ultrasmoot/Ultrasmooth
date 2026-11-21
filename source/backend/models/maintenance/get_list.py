import models.maintenance.model as _m

class MaintenanceModelGetList:
    # ---------- lookups ----------
    @staticmethod
    def get(record_id: int):
        conn = _m.get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(_m._SELECT_WITH_NAMES + " WHERE m.id = %s", (record_id,))
            return cur.fetchone()
        finally:
            conn.close()

    @staticmethod
    def list(user: dict, status_group: str = None, resource_id: int = None):
        """Admins see every record everyone else sees only their own reports."""
        conn = _m.get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            sql = _m._SELECT_WITH_NAMES
            clauses, params = [], []
            if user["role"] != "admin":
                clauses.append("m.reported_by = %s")
                params.append(user["id"])
            groups = {
                "reported": ("Reported",),
                "open": _m.BLOCKING_STATUSES,
                "closed": ("Resolved", "Dismissed"),
            }
            if status_group in groups:
                marks = ", ".join(["%s"] * len(groups[status_group]))
                clauses.append(f"m.status IN ({marks})")
                params.extend(groups[status_group])
            if resource_id is not None:
                clauses.append("m.resource_id = %s")
                params.append(resource_id)
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)
            sql += " ORDER BY m.created_at DESC, m.id DESC"
            cur.execute(sql, tuple(params))
            return cur.fetchall()
        finally:
            conn.close()

    # ---------- internal: lock the resource, then the record (same order everywhere) ----------
    @staticmethod
    def _lock_record(conn, record_id: int):
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT resource_id FROM maintenance_records WHERE id = %s", (record_id,))
        row = cur.fetchone()
        if not row:
            raise _m.ValidationError("Maintenance record not found.")
        cur.execute("SELECT id, status FROM resources WHERE id = %s FOR UPDATE", (row["resource_id"],))
        resource = cur.fetchone()
        cur.execute("SELECT * FROM maintenance_records WHERE id = %s FOR UPDATE", (record_id,))
        record = cur.fetchone()
        return cur, resource, record
