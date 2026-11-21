import mysql.connector
import models.maintenance.model as _m

class MaintenanceModelHasBlockingIssueStatusAfterMaintena:
    @staticmethod
    def _has_blocking_issue(cur, resource_id: int, exclude_record_id: int = None) -> bool:
        sql = """SELECT COUNT(*) AS n FROM maintenance_records
                 WHERE resource_id = %s AND status IN ('Open','In Progress')"""
        params = [resource_id]
        if exclude_record_id:
            sql += " AND id != %s"
            params.append(exclude_record_id)
        # FOR UPDATE = locking read: sees the latest committed rows instead of the
        sql += " FOR UPDATE"
        cur.execute(sql, tuple(params))
        return cur.fetchone()["n"] > 0

    @staticmethod
    def _status_after_maintenance(cur, resource_id: int) -> str:
        """After maintenance, the resource is 'In Use' if someone is still checked in; otherwise, it is 'Available'. 
        This prevents others from checking in while a session is still active"""
        cur.execute(
            """SELECT COUNT(*) AS n FROM bookings
               WHERE resource_id = %s AND status = 'Approved'
                 AND checked_in_at IS NOT NULL AND checked_out_at IS NULL""",
            (resource_id,),
        )
        return "In Use" if cur.fetchone()["n"] > 0 else "Available"

    @classmethod
    def report(cls, data: dict, reporter: dict):
        """Anyone can report an issue. Non-admin reports need admin approval before the resource goes into Maintenance. 
        Admin reports are confirmed immediately"""
        try:
            resource_id = int(data.get("resource_id"))
        except (TypeError, ValueError, OverflowError): 
            raise _m.ValidationError("resource_id must be a valid resource.")
        description = cls._clean_description(data.get("description"))
        issue_date = cls._clean_date(data.get("date"))
        is_admin = reporter["role"] == "admin"
        status = cls._clean_status(data.get("status") or "Open") if is_admin else "Reported"

        conn = _m.get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            # Lock the resource row so a concurrent report/confirm/resolve for the same resource cannot interleave with this one.
            cur.execute(
                "SELECT id, status, is_archived FROM resources WHERE id = %s FOR UPDATE",
                (resource_id,),
            )
            resource = cur.fetchone()
            if not resource or resource["is_archived"]:
                raise _m.ValidationError("The selected resource does not exist.")

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
            _m.events.maintenance_reported(conn, new_id)  
            conn.commit()
        except _m.ValidationError:
            conn.rollback()
            raise
        except mysql.connector.IntegrityError:
            conn.rollback()
            raise _m.ValidationError("The selected resource does not exist.")
        except mysql.connector.DataError:
            conn.rollback()
            raise _m.ValidationError("Some of the submitted values are too long or invalid.")
        finally:
            conn.close()
        return cls.get(new_id)
