import mysql.connector
from database.db import get_connection

VALID_STATUSES = {"Available", "In Use", "Maintenance"}
REQUIRED_FIELDS = ["name", "type", "category", "location", "owner"]

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
                        #insert into resources
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
                #update resources
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

    @classmethod
    def archive(cls, resource_id: int):
    # AD-1: archiving hides the resource from the active list rather than deleting it
        if not cls.get(resource_id):
            raise ValidationError("Resource not found.")
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE resources SET is_archived = 1 WHERE id = %s", (resource_id,))
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def get(resource_id: int):
        #get resource
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM resources WHERE id = %s", (resource_id,))
            return cur.fetchone()
        finally:
            conn.close()

    SORTABLE_COLUMNS = {"name", "category", "location", "status"}

    @staticmethod
    def list(search: str = None, category: str = None, location: str = None,
              status: str = None, include_archived: bool = False,
              sort_by: str = "name", sort_dir: str = "asc"):
        #SRS-1: search by keyword, filter/sort by category, location, availability and status
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

            column = sort_by if sort_by in ResourceModel.SORTABLE_COLUMNS else "name"
            direction = "DESC" if str(sort_dir).lower() == "desc" else "ASC"
            sql += f" ORDER BY {column} {direction}"

            cur.execute(sql, tuple(params))
            return cur.fetchall()
        finally:
            conn.close()
    