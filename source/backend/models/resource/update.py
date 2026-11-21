# update resource details
import models.resource.model as _m

class ResourceModelUpdate:
    @classmethod
    def update(cls, resource_id: int, data: dict, actor_id: int = None):
        existing = cls.get(resource_id)
        if not existing:
            raise _m.ValidationError("Resource not found.")
        cls._validate(data, partial=True)
        details = cls._clean_details(data)

        new_status = data.get("status")
        # maintenance status can only be changed through maintenance records
        if (
            new_status is not None
            and new_status != existing["status"]
            and "Maintenance" in (new_status, existing["status"])
        ):
            raise _m.ValidationError(_m.MAINTENANCE_MANAGED_MSG)

        merged = {**existing, **{k: v for k, v in data.items() if v is not None}}
        conn = _m.get_connection()
        try:
            cur = conn.cursor()
            # keep status unchanged to avoid overwriting maintenance updates
            cur.execute(
                """UPDATE resources
                   SET name=%s, type=%s, category=%s, location=%s, owner=%s
                   WHERE id=%s""",
                (
                    merged["name"].strip(),
                    merged["type"].strip(),
                    merged["category"].strip(),
                    merged["location"].strip(),
                    merged["owner"].strip(),
                    resource_id,
                ),
            )
            if details:
                columns = ", ".join(f"{_m.DETAIL_COLUMNS[k]} = %s" for k in details)
                cur.execute(f"UPDATE resources SET {columns} WHERE id = %s", tuple(details.values()) + (resource_id,))
            if new_status is not None and new_status != existing["status"]:
                # prevent changes if the resource has entered maintenance
                cur.execute(
                    "UPDATE resources SET status=%s WHERE id=%s AND status <> 'Maintenance'",
                    (new_status, resource_id),
                )
                if cur.rowcount == 0:
                    conn.rollback()
                    raise _m.ValidationError(_m.MAINTENANCE_MANAGED_MSG)
            if actor_id is not None:
                _m.events.resource_changed(conn, "resource.updated", resource_id, actor_id)
            conn.commit()
            return cls.get(resource_id)
        finally:
            conn.close()