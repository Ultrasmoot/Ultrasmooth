import datetime
import mysql.connector

from database.db import get_connection

BLOCKING_STATUSES = ("Open", "In Progress")  
EDITABLE_STATUSES = {"Open", "In Progress"}  
MAX_DESCRIPTION_LENGTH = 500 
MAX_REASON_LENGTH = 255 

_SELECT_WITH_NAMES = """
    SELECT m.*,
           r.name          AS resource_name,
           r.resource_code AS resource_code,
           u.full_name     AS reporter_name,
           u.email         AS reporter_email
    FROM maintenance_records m
    JOIN resources r ON r.id = m.resource_id
    JOIN users u     ON u.id = m.reported_by
"""


class ValidationError(Exception):
    pass


class MaintenanceModel:

    @staticmethod
    def _clean_description(value):
        if value is not None and not isinstance(value, str):
            raise ValidationError("description must be text.")
        description = (value or "").strip()
        if not description:
            raise ValidationError("description is required.")
        if len(description) > MAX_DESCRIPTION_LENGTH:
            raise ValidationError(
                f"description must be at most {MAX_DESCRIPTION_LENGTH} characters "
                f"(currently {len(description)})."
            )
        return description

    @staticmethod
    def _clean_reason(value):
        if value is not None and not isinstance(value, str):
            raise ValidationError("reason must be text.")
        reason = (value or "").strip()
        if not reason:
            raise ValidationError("reason is required when rejecting a report.")
        if len(reason) > MAX_REASON_LENGTH:
            raise ValidationError(
                f"reason must be at most {MAX_REASON_LENGTH} characters (currently {len(reason)})."
            )
        return reason

    @staticmethod
    def _clean_date(value):
        if not value:
            raise ValidationError("date is required.")
        if not isinstance(value, str):
            raise ValidationError("date must be a valid date (YYYY-MM-DD).")
        try:
            parsed = datetime.date.fromisoformat(value.strip()[:10])
        except ValueError:
            raise ValidationError("date must be a valid date (YYYY-MM-DD).")
        # An issue may have been noticed earlier, but it cannot be dated in the future.
        if parsed > datetime.date.today():
            raise ValidationError("date cannot be in the future.")
        return parsed

    @staticmethod
    def _clean_status(value):
        status = value.strip() if isinstance(value, str) else None
        if status not in EDITABLE_STATUSES:
            raise ValidationError("status must be 'Open' or 'In Progress'.")
        return status

    # ---------- lookups ----------
    @staticmethod
    def get(record_id: int):
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(_SELECT_WITH_NAMES + " WHERE m.id = %s", (record_id,))
            return cur.fetchone()
        finally:
            conn.close()

    @staticmethod
    def list(user: dict, status_group: str = None, resource_id: int = None):
        """Admins see every record (optionally one group); everyone else sees only their own reports."""
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            sql = _SELECT_WITH_NAMES
            clauses, params = [], []
            if user["role"] != "admin":
                clauses.append("m.reported_by = %s")
                params.append(user["id"])
            groups = {
                "reported": ("Reported",),
                "open": BLOCKING_STATUSES,
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

    @staticmethod
    def _lock_record(conn, record_id: int):
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT resource_id FROM maintenance_records WHERE id = %s", (record_id,))
        row = cur.fetchone()
        if not row:
            raise ValidationError("Maintenance record not found.")
        cur.execute("SELECT id, status FROM resources WHERE id = %s FOR UPDATE", (row["resource_id"],))
        resource = cur.fetchone()
        cur.execute("SELECT * FROM maintenance_records WHERE id = %s FOR UPDATE", (record_id,))
        record = cur.fetchone()
        return cur, resource, record

    @staticmethod
    def _has_blocking_issue(cur, resource_id: int, exclude_record_id: int = None) -> bool:
        sql = """SELECT COUNT(*) AS n FROM maintenance_records
                 WHERE resource_id = %s AND status IN ('Open','In Progress')"""
        params = [resource_id]
        if exclude_record_id:
            sql += " AND id != %s"
            params.append(exclude_record_id)
        sql += " FOR UPDATE"
        cur.execute(sql, tuple(params))
        return cur.fetchone()["n"] > 0

    @classmethod
    def report(cls, data: dict, reporter: dict):
        """Anyone may report. A report from a non-admin is only 'Reported' - the
        resource is untouched until an admin confirms it. An admin's own report
        is confirmed immediately, so the resource moves to Maintenance at once."""
        try:
            resource_id = int(data.get("resource_id"))
        except (TypeError, ValueError, OverflowError):  # OverflowError: int(Infinity)
            raise ValidationError("resource_id must be a valid resource.")
        description = cls._clean_description(data.get("description"))
        issue_date = cls._clean_date(data.get("date"))
        is_admin = reporter["role"] == "admin"
        status = cls._clean_status(data.get("status") or "Open") if is_admin else "Reported"

        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT id, status, is_archived FROM resources WHERE id = %s FOR UPDATE",
                (resource_id,),
            )
            resource = cur.fetchone()
            if not resource or resource["is_archived"]:
                raise ValidationError("The selected resource does not exist.")

            if is_admin:
                cur.execute(
                    """INSERT INTO maintenance_records
                       (resource_id, reported_by, description, status, issue_date, confirmed_by, confirmed_at)
                       VALUES (%s, %s, %s, %s, %s, %s, NOW())""",
                    (resource_id, reporter["id"], description, status, issue_date, reporter["id"]),
                )
                new_id = cur.lastrowid
                cur.execute("UPDATE resources SET status = 'Maintenance' WHERE id = %s", (resource_id,))
            else:
                cur.execute(
                    """INSERT INTO maintenance_records (resource_id, reported_by, description, status, issue_date)
                       VALUES (%s, %s, %s, 'Reported', %s)""",
                    (resource_id, reporter["id"], description, issue_date),
                )
                new_id = cur.lastrowid
            conn.commit()
        except ValidationError:
            conn.rollback()
            raise
        except mysql.connector.IntegrityError:
            conn.rollback()
            raise ValidationError("The selected resource does not exist.")
        except mysql.connector.DataError:
            conn.rollback()
            raise ValidationError("Some of the submitted values are too long or invalid.")
        finally:
            conn.close()
        return cls.get(new_id)

    # ---------- admin: confirm / dismiss a reported issue ----------
    @classmethod
    def confirm(cls, record_id: int, admin_id: int):
        conn = get_connection()
        try:
            cur, resource, record = cls._lock_record(conn, record_id)
            if record["status"] != "Reported":
                raise ValidationError(f"This report was already {record['status'].lower()}.")
            if resource["status"] != "Maintenance":
                cur.execute("UPDATE resources SET status = 'Maintenance' WHERE id = %s", (resource["id"],))
            cur.execute(
                """UPDATE maintenance_records
                   SET status = 'Open', confirmed_by = %s, confirmed_at = NOW() WHERE id = %s""",
                (admin_id, record_id),
            )
            conn.commit()
        except ValidationError:
            conn.rollback()
            raise
        finally:
            conn.close()
        return cls.get(record_id)

    @classmethod
    def dismiss(cls, record_id: int, admin_id: int, reason=None):
        """Rejects a report. The reason is required and is shown to the reporter."""
        reason = cls._clean_reason(reason)
        conn = get_connection()
        try:
            cur, _resource, record = cls._lock_record(conn, record_id)
            if record["status"] != "Reported":
                raise ValidationError(f"This report was already {record['status'].lower()}.")
            cur.execute(
                """UPDATE maintenance_records
                   SET status = 'Dismissed', dismiss_reason = %s, closed_by = %s, closed_at = NOW()
                   WHERE id = %s""",
                (reason, admin_id, record_id),
            )
            conn.commit()
        except ValidationError:
            conn.rollback()
            raise
        finally:
            conn.close()
        return cls.get(record_id)

    @classmethod
    def update(cls, record_id: int, data: dict):
        if "resource_id" in data and data["resource_id"] is not None:
            try:
                new_resource = int(data["resource_id"])
            except (TypeError, ValueError, OverflowError):
                raise ValidationError("resource_id cannot be changed.")
        else:
            new_resource = None

        conn = get_connection()
        try:
            cur, _resource, record = cls._lock_record(conn, record_id)
            if record["status"] not in EDITABLE_STATUSES:
                raise ValidationError(
                    f"A {record['status'].lower()} record cannot be edited."
                )
            if new_resource is not None and new_resource != record["resource_id"]:
                raise ValidationError("resource_id cannot be changed.")

            description = (
                cls._clean_description(data["description"]) if "description" in data
                else record["description"]
            )
            issue_date = (
                cls._clean_date(data["date"]) if "date" in data else record["issue_date"]
            )
            status = cls._clean_status(data["status"]) if "status" in data else record["status"]

            cur.execute(
                "UPDATE maintenance_records SET description=%s, status=%s, issue_date=%s WHERE id=%s",
                (description, status, issue_date, record_id),
            )
            conn.commit()
        except ValidationError:
            conn.rollback()
            raise
        except mysql.connector.DataError:
            conn.rollback()
            raise ValidationError("Some of the submitted values are too long or invalid.")
        finally:
            conn.close()
        return cls.get(record_id)

    @classmethod
    def resolve(cls, record_id: int, admin_id: int):
        """Marks the issue Resolved. The resource only returns to Available when
        no other Open / In Progress issue still exists for it."""
        conn = get_connection()
        try:
            cur, resource, record = cls._lock_record(conn, record_id)
            if record["status"] not in EDITABLE_STATUSES:
                raise ValidationError(f"This record is {record['status'].lower()}, so it cannot be resolved.")
            cur.execute(
                """UPDATE maintenance_records
                   SET status = 'Resolved', closed_by = %s, closed_at = NOW() WHERE id = %s""",
                (admin_id, record_id),
            )
            if resource["status"] == "Maintenance" and not cls._has_blocking_issue(
                cur, resource["id"], exclude_record_id=record_id
            ):
                cur.execute("UPDATE resources SET status = 'Available' WHERE id = %s", (resource["id"],))
            conn.commit()
        except ValidationError:
            conn.rollback()
            raise
        finally:
            conn.close()
        return cls.get(record_id)

    # ---------- admin: put a resource back to Available ----------
    @classmethod
    def release_resource(cls, resource_id: int, admin_id: int) -> int:
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT id, status FROM resources WHERE id = %s FOR UPDATE", (resource_id,))
            resource = cur.fetchone()
            if not resource:
                raise ValidationError("Resource not found.")
            if resource["status"] != "Maintenance":
                raise ValidationError("This resource is not in Maintenance.")
            cur.execute(
                (admin_id, resource_id),
            )
            closed = cur.rowcount
            cur.execute("UPDATE resources SET status = 'Available' WHERE id = %s", (resource_id,))
            conn.commit()
            return closed
        except ValidationError:
            conn.rollback()
            raise
        finally:
            conn.close()