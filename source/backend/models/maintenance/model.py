import datetime

import mysql.connector

from database.db import get_connection
from services.events import service as events 

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


from models.maintenance.clean_description_clean_reason import MaintenanceModelCleanDescriptionCleanReason 
from models.maintenance.get_list import MaintenanceModelGetList 
from models.maintenance.has_blocking_issue_status_after_maintenace import MaintenanceModelHasBlockingIssueStatusAfterMaintena 
from models.maintenance.confirm_dismiss import MaintenanceModelConfirmDismiss  
from models.maintenance.update import MaintenanceModelUpdate  


class MaintenanceModel(MaintenanceModelCleanDescriptionCleanReason, MaintenanceModelGetList, MaintenanceModelHasBlockingIssueStatusAfterMaintena, MaintenanceModelConfirmDismiss, MaintenanceModelUpdate):
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
                cur.execute("UPDATE resources SET status = %s WHERE id = %s",
                            (cls._status_after_maintenance(cur, resource["id"]), resource["id"]))
            events.maintenance_resolved(conn, record_id, admin_id) 
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
        """Moves a resource from Maintenance to Available. All Open and In Progress issues are marked as Resolved
        except unreviewed reports. Returns the number of issues resolved."""
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
                """UPDATE maintenance_records
                   SET status = 'Resolved', closed_by = %s, closed_at = NOW()
                   WHERE resource_id = %s AND status IN ('Open','In Progress')""",
                (admin_id, resource_id),
            )
            closed = cur.rowcount
            cur.execute("UPDATE resources SET status = %s WHERE id = %s",
                        (cls._status_after_maintenance(cur, resource_id), resource_id))
            events.maintenance_released(conn, resource_id, admin_id, closed)
            conn.commit()
            return closed
        except ValidationError:
            conn.rollback()
            raise
        finally:
            conn.close()
