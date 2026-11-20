# archive and unarchive resource actions
import models.resource.model as _m

class ResourceModelArchiveUnarchive:
    @classmethod
    def archive(cls, resource_id: int, actor_id: int = None):
        """Archive a resource without deleting it."""
        existing = cls.get(resource_id)
        if not existing:
            raise _m.ValidationError("Resource not found.")
        conn = _m.get_connection()
        try:
            cur = conn.cursor()
            # lock the resource before checking its bookings
            cur.execute("SELECT status FROM resources WHERE id = %s FOR UPDATE", (resource_id,))
            row = cur.fetchone()
            if row and row[0] == "In Use":
                conn.rollback()
                raise _m.ValidationError("This resource is currently In Use and cannot be archived.")
            cur.execute(
                """SELECT COUNT(*) FROM bookings
                   WHERE resource_id = %s AND status IN ('Pending','Approved')
                     AND end_time > NOW() AND checked_out_at IS NULL""",
                (resource_id,),
            )
            if cur.fetchone()[0] > 0:
                conn.rollback()
                raise _m.ValidationError(
                    "This resource has active bookings (pending or approved) and cannot be archived."
                )
            cur.execute("UPDATE resources SET is_archived = 1 WHERE id = %s", (resource_id,))
            if actor_id is not None:
                _m.events.resource_changed(conn, "resource.archived", resource_id, actor_id)
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def unarchive(cls, resource_id: int, actor_id: int = None):
        """Restore an archived resource."""
        if not cls.get(resource_id):
            raise _m.ValidationError("Resource not found.")
        conn = _m.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE resources SET is_archived = 0 WHERE id = %s", (resource_id,))
            if actor_id is not None:
                _m.events.resource_changed(conn, "resource.unarchived", resource_id, actor_id)
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def get(resource_id: int):
        conn = _m.get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM resources WHERE id = %s", (resource_id,))
            return cur.fetchone()
        finally:
            conn.close()

    @staticmethod
    def _clean_details(data: dict) -> dict:
        """Validate optional resource details and clear blank values."""
        out = _m.ResourceModel._clean_text_details(data)
        if "capacity" in data:
            out["capacity"] = _m.ResourceModel._clean_capacity(data["capacity"])
        if "features" in data:
            out["features"] = _m.ResourceModel._clean_features(data["features"])
        return out