# create resources and clean text details
import mysql.connector
import models.resource.model as _m

class ResourceModelCreateCleanTextDetails:
    @classmethod
    def create(cls, data: dict, actor_id: int = None):
        cls._validate(data)
        details = cls._clean_details(data)
        # maintenance status must come from a confirmed maintenance record
        if data.get("status") == "Maintenance":
            raise _m.ValidationError(_m.MAINTENANCE_MANAGED_MSG)
        conn = _m.get_connection()
        try:
            # retry if another request generates the same resource code
            attempts = 3
            for attempt in range(attempts):
                code = cls._next_resource_code(conn)
                cur = conn.cursor()
                try:
                    cur.execute(
                        """INSERT INTO resources (resource_code, name, type, category, location, owner, status,
                                                   building, floor_level, capacity, features, usage_notes)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (
                            code,
                            data["name"].strip(),
                            data["type"].strip(),
                            data["category"].strip(),
                            data["location"].strip(),
                            data["owner"].strip(),
                            data.get("status", "Available"),
                            details.get("building"),
                            details.get("floor"),
                            details.get("capacity"),
                            details.get("features"),
                            details.get("usage_notes"),
                        ),
                    )
                    new_id = cur.lastrowid
                    if actor_id is not None:
                        _m.events.resource_changed(conn, "resource.created", new_id, actor_id)
                    conn.commit()
                    return cls.get(new_id)
                except mysql.connector.IntegrityError:
                    conn.rollback()
                    if attempt == attempts - 1:
                        raise _m.ValidationError("Could not allocate a resource code, please retry.")
        finally:
            conn.close()

    @staticmethod
    def _clean_text_details(data: dict) -> dict:
        out = {}
        for key, limit in _m.DETAIL_TEXT_LIMITS.items():
            if key in data:
                value = data[key]
                if value is None:
                    out[key] = None
                    continue
                if not isinstance(value, str):
                    raise _m.ValidationError(f"'{key}' must be text.")
                value = value.strip()
                if len(value) > limit:
                    raise _m.ValidationError(f"'{key}' must be at most {limit} characters.")
                out[key] = value or None
        return out