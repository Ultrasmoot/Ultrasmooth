import mysql.connector

from database.db import get_connection

VALID_STATUSES = {"Available", "In Use", "Maintenance"}
REQUIRED_FIELDS = ["name", "type", "category", "location", "owner"]
MAX_FIELD_LENGTHS = {"name": 150, "type": 100, "category": 100, "location": 150, "owner": 150}


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
        #SRS-2: required fields must be filled 
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

    @classmethod
    def create(cls, data: dict):
        cls._validate(data)
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
                        """INSERT INTO resources (resource_code, name, type, category, location, owner, status)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                        (
                            code,
                            data["name"].strip(),
                            data["type"].strip(),
                            data["category"].strip(),
                            data["location"].strip(),
                            data["owner"].strip(),
                            data.get("status", "Available"),
                        ),
                    )
                    conn.commit()
                    return cls.get(cur.lastrowid)
                except mysql.connector.IntegrityError:
                    conn.rollback()
                    if attempt == attempts - 1:
                        raise ValidationError("Could not allocate a resource code, please retry.")
        finally:
            conn.close()

    @classmethod
    def update(cls, resource_id: int, data: dict):
        existing = cls.get(resource_id)
        if not existing:
            raise ValidationError("Resource not found.")
        cls._validate(data, partial=True)

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
            if new_status is not None and new_status != existing["status"]:
                cur.execute(
                    "UPDATE resources SET status=%s WHERE id=%s AND status <> 'Maintenance'",
                    (new_status, resource_id),
                )
                if cur.rowcount == 0:
                    conn.rollback()
                    raise ValidationError(MAINTENANCE_MANAGED_MSG)
            conn.commit()
            return cls.get(resource_id)
        finally:
            conn.close()

    @classmethod
    def archive(cls, resource_id: int):
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
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def unarchive(cls, resource_id: int):
        # Reverse of archive(): the resource returns to the active list with the status it had
        if not cls.get(resource_id):
            raise ValidationError("Resource not found.")
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE resources SET is_archived = 0 WHERE id = %s", (resource_id,))
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def get(resource_id: int): # get resource
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
        # search by keyword, filter/sort by category, location, availability and status
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