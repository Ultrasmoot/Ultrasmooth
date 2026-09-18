import mysql.connector
from database.db import get_connection

VALID_STATUSES = {"Available", "In Use", "Maintenance"}
REQUIRED_FIELDS = ["name", "type", "category", "location", "owner"]

class ValidationError(Exception):
    pass

class ResourceModel:

    # Jirat
    @staticmethod
    def _next_resource_code(conn):
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM resources")
        count = cur.fetchone()[0]
        return f"RES-{count + 1:04d}"

    @staticmethod
    def _validate(data: dict, partial: bool = False):
        """SRS-2: required fields must be filled before saving; missing or
        invalid data blocks the save with a validation message."""
        for field in REQUIRED_FIELDS:
            if not partial or field in data:
                if not (data.get(field) or "").strip():
                    raise ValidationError(f"'{field}' is required.")

        status = data.get("status")
        if status is not None and status not in VALID_STATUSES:
            raise ValidationError(f"Status must be one of: {', '.join(sorted(VALID_STATUSES))}.")

    @classmethod
    def create(cls, data: dict):
        cls._validate(data)
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

        merged = {**existing, **{k: v for k, v in data.items() if v is not None}}
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """UPDATE resources
                   SET name=%s, type=%s, category=%s, location=%s, owner=%s, status=%s
                   WHERE id=%s""",
                (
                    merged["name"].strip(),
                    merged["type"].strip(),
                    merged["category"].strip(),
                    merged["location"].strip(),
                    merged["owner"].strip(),
                    merged["status"],
                    resource_id,
                ),
            )
            conn.commit()
            return cls.get(resource_id)
        finally:
            conn.close()