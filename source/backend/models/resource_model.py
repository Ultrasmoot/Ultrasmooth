import mysql.connector

from database.db import get_connection
from services import events  

VALID_STATUSES = {"Available", "In Use", "Maintenance"}
REQUIRED_FIELDS = ["name", "type", "category", "location", "owner"]
MAX_FIELD_LENGTHS = {"name": 150, "type": 100, "category": 100, "location": 150, "owner": 150}


# optional details shown on the resource detail page
DETAIL_COLUMNS = {"building": "building", "floor": "floor_level", "capacity": "capacity",
                  "features": "features", "usage_notes": "usage_notes"}
DETAIL_TEXT_LIMITS = {"building": 100, "floor": 50, "usage_notes": 1000}
MAX_CAPACITY = 100000
MAX_FEATURES = 15
MAX_FEATURE_LENGTH = 40
MAX_FEATURES_TOTAL = 500


MAINTENANCE_MANAGED_MSG = (
    "The 'Maintenance' status is managed through Maintenance records "
    "(report an issue to enter it, resolve the issue to leave it)."
)


class ValidationError(Exception):
    pass


class ResourceModel:

    @staticmethod
    def _next_resource_code(conn):
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM resources")
        count = cur.fetchone()[0]
        return f"RES-{count + 1:04d}"

    @staticmethod
    def _validate(data: dict, partial: bool = False):
        # SRS-2 : required fields must be filled before saving. If not -> validation message appear
        for field in REQUIRED_FIELDS:
            if not partial or field in data:
                value = data.get(field)
                if value is not None and not isinstance(value, str):
                    raise ValidationError(f"'{field}' must be text.")
                if not (value or "").strip():
                    raise ValidationError(f"'{field}' is required.")
                if len(value.strip()) > MAX_FIELD_LENGTHS[field]:
                    raise ValidationError(
                        f"'{field}' must be at most {MAX_FIELD_LENGTHS[field]} characters."
                    )

        status = data.get("status")
        if status is not None and (not isinstance(status, str) or status not in VALID_STATUSES):
            raise ValidationError(f"Status must be one of: {', '.join(sorted(VALID_STATUSES))}.")

    @staticmethod
    def _clean_details(data: dict) -> dict:
        # validate the optional detail fields that are present in `data`
        out = {}
        for key, limit in DETAIL_TEXT_LIMITS.items():
            if key in data:
                value = data[key]
                if value is None:
                    out[key] = None
                    continue
                if not isinstance(value, str):
                    raise ValidationError(f"'{key}' must be text.")
                value = value.strip()
                if len(value) > limit:
                    raise ValidationError(f"'{key}' must be at most {limit} characters.")
                out[key] = value or None
        if "capacity" in data:
            value = data["capacity"]
            if value is None or (isinstance(value, str) and not value.strip()):
                out["capacity"] = None
            else:
                if isinstance(value, bool) or not isinstance(value, (int, str)):
                    raise ValidationError("'capacity' must be a whole number.")
                try:
                    number = int(value)
                except ValueError:
                    raise ValidationError("'capacity' must be a whole number.")
                if number < 1 or number > MAX_CAPACITY:
                    raise ValidationError(f"'capacity' must be between 1 and {MAX_CAPACITY}.")
                out["capacity"] = number
        if "features" in data:
            value = data["features"]
            if value is None:
                out["features"] = None
            else:
                items = value if isinstance(value, list) else (value.split(",") if isinstance(value, str) else None)
                if items is None:
                    raise ValidationError("'features' must be a list of short texts.")
                cleaned, seen = [], set()
                for item in items:
                    if not isinstance(item, str):
                        raise ValidationError("'features' must be a list of short texts.")
                    item = " ".join(item.split())
                    if not item or item.lower() in seen:
                        continue
                    if "," in item:
                        raise ValidationError("A feature cannot contain a comma.")
                    if len(item) > MAX_FEATURE_LENGTH:
                        raise ValidationError(f"Each feature must be at most {MAX_FEATURE_LENGTH} characters.")
                    seen.add(item.lower())
                    cleaned.append(item)
                if len(cleaned) > MAX_FEATURES:
                    raise ValidationError(f"At most {MAX_FEATURES} features.")
                joined = ",".join(cleaned)
                if len(joined) > MAX_FEATURES_TOTAL:
                    raise ValidationError("The features list is too long.")
                out["features"] = joined or None
        return out

    @classmethod
    def create(cls, data: dict, actor_id: int = None):
        cls._validate(data)
        details = cls._clean_details(data)
        # a new resource cannot start in Maintenance and only comes from a confirmed maintenance record.
        if data.get("status") == "Maintenance":
            raise ValidationError(MAINTENANCE_MANAGED_MSG)
        conn = get_connection()
        try:
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
                        events.resource_changed(conn, "resource.created", new_id, actor_id)   # Iteration 5
                    conn.commit()
                    return cls.get(new_id)
                except mysql.connector.IntegrityError:
                    conn.rollback()
                    if attempt == attempts - 1:
                        raise ValidationError("Could not allocate a resource code, please retry.")
        finally:
            conn.close()

    @classmethod
    def update(cls, resource_id: int, data: dict, actor_id: int = None):
        existing = cls.get(resource_id)
        if not existing:
            raise ValidationError("Resource not found.")
        cls._validate(data, partial=True)
        details = cls._clean_details(data)

        # the resource API may not move a resource into or out of Maintenance
        new_status = data.get("status")
        if (
            new_status is not None
            and new_status != existing["status"]
            and "Maintenance" in (new_status, existing["status"])
        ):
            raise ValidationError(MAINTENANCE_MANAGED_MSG)

        merged = {**existing, **{k: v for k, v in data.items() if v is not None}}
        conn = get_connection()
        try:
            cur = conn.cursor()
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

            if details:   # only the detail fields that were sent are touched (null/blank clears)
                columns = ", ".join(f"{DETAIL_COLUMNS[k]} = %s" for k in details)
                cur.execute(f"UPDATE resources SET {columns} WHERE id = %s", tuple(details.values()) + (resource_id,))

            if new_status is not None and new_status != existing["status"]:
                cur.execute(
                    "UPDATE resources SET status=%s WHERE id=%s AND status <> 'Maintenance'",
                    (new_status, resource_id),
                )
                if cur.rowcount == 0:
                    conn.rollback()
                    raise ValidationError(MAINTENANCE_MANAGED_MSG)

            if actor_id is not None:
                events.resource_changed(conn, "resource.updated", resource_id, actor_id)   # Iteration 5
            conn.commit()
            return cls.get(resource_id)
        finally:
            conn.close()


    @classmethod
    def archive(cls, resource_id: int, actor_id: int = None):
        # AD-1: archiving hides the resource from the active list rather than deleting it
        existing = cls.get(resource_id)
        if not existing:
            raise ValidationError("Resource not found.")
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT status FROM resources WHERE id = %s FOR UPDATE", (resource_id,))
            row = cur.fetchone()
            if row and row[0] == "In Use":
                conn.rollback()
                raise ValidationError("This resource is currently In Use and cannot be archived.")
            cur.execute(
                """SELECT COUNT(*) FROM bookings
                   WHERE resource_id = %s AND status IN ('Pending','Approved')
                     AND end_time > NOW() AND checked_out_at IS NULL""",
                (resource_id,),
            )
            if cur.fetchone()[0] > 0:
                conn.rollback()
                raise ValidationError(
                    "This resource has active bookings (pending or approved) and cannot be archived."
                )
            cur.execute("UPDATE resources SET is_archived = 1 WHERE id = %s", (resource_id,))
            if actor_id is not None:
                events.resource_changed(conn, "resource.archived", resource_id, actor_id)   # Iteration 5
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def unarchive(cls, resource_id: int, actor_id: int = None):
        # reverse of archive()
        if not cls.get(resource_id):
            raise ValidationError("Resource not found.")
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE resources SET is_archived = 0 WHERE id = %s", (resource_id,))

            if actor_id is not None:
                events.resource_changed(conn, "resource.unarchived", resource_id, actor_id)   # Iteration 5
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def get(resource_id: int):
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM resources WHERE id = %s", (resource_id,))
            return cur.fetchone()
        finally:
            conn.close()

    SORTABLE_COLUMNS = {
        "name": "name",
        "category": "category",
        "location": "location",
        "status": "FIELD(status, 'Available', 'In Use', 'Maintenance')",
        "availability": "CASE WHEN status = 'Available' THEN 0 ELSE 1 END",
    }
    DEFAULT_SORT = "status"

    @staticmethod
    def list(search: str = None, category: str = None, location: str = None,
              status: str = None, include_archived: bool = False,
              sort_by: str = DEFAULT_SORT, sort_dir: str = "asc"):
        # SRS-1: search by keyword, filter/sort by category, location, availability and status
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            clauses = []
            params = []

            if not include_archived:
                clauses.append("is_archived = 0")
            if search:
                clauses.append("name LIKE %s")
                params.append(f"%{search}%")
            if category:
                clauses.append("category = %s")
                params.append(category)
            if location:
                clauses.append("location = %s")
                params.append(location)
            if status:
                clauses.append("status = %s")
                params.append(status)

            sql = "SELECT * FROM resources"
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)

            order_expr = ResourceModel.SORTABLE_COLUMNS.get(
                sort_by, ResourceModel.SORTABLE_COLUMNS[ResourceModel.DEFAULT_SORT]
            )
            direction = "DESC" if str(sort_dir).lower() == "desc" else "ASC"
            sql += f" ORDER BY is_archived ASC, {order_expr} {direction}, name ASC, id ASC"

            cur.execute(sql, tuple(params))
            return cur.fetchall()
        finally:
            conn.close()
