import mysql.connector
import models.maintenance.model as _m

class MaintenanceModelUpdate:
    # ---------- edit / resolve ----------
    @classmethod
    def update(cls, record_id: int, data: dict, actor_id: int = None):
        if "resource_id" in data and data["resource_id"] is not None:
            try:
                new_resource = int(data["resource_id"])
            except (TypeError, ValueError, OverflowError):
                raise _m.ValidationError("resource_id cannot be changed.")
        else:
            new_resource = None

        conn = _m.get_connection()
        try:
            cur, _resource, record = cls._lock_record(conn, record_id)
            if record["status"] not in _m.EDITABLE_STATUSES:
                raise _m.ValidationError(
                    f"A {record['status'].lower()} record cannot be edited."
                )
            if new_resource is not None and new_resource != record["resource_id"]:
                raise _m.ValidationError("resource_id cannot be changed.")

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
            if actor_id is not None:
                _m.events.maintenance_updated(conn, record_id, actor_id) 
            conn.commit()
        except _m.ValidationError:
            conn.rollback()
            raise
        except mysql.connector.DataError:
            conn.rollback()
            raise _m.ValidationError("Some of the submitted values are too long or invalid.")
        finally:
            conn.close()
        return cls.get(record_id)
