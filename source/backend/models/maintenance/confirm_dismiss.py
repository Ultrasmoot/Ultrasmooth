import models.maintenance.model as _m

class MaintenanceModelConfirmDismiss:
    # ---------- admin: confirm / dismiss a reported issue ----------
    @classmethod
    def confirm(cls, record_id: int, admin_id: int):
        conn = _m.get_connection()
        try:
            cur, resource, record = cls._lock_record(conn, record_id)
            if record["status"] != "Reported":
                raise _m.ValidationError(f"This report was already {record['status'].lower()}.")
            if resource["status"] != "Maintenance":
                cur.execute("UPDATE resources SET status = 'Maintenance' WHERE id = %s", (resource["id"],))
            cur.execute(
                """UPDATE maintenance_records
                   SET status = 'Open', confirmed_by = %s, confirmed_at = NOW() WHERE id = %s""",
                (admin_id, record_id),
            )
            _m.events.maintenance_confirmed(conn, record_id, admin_id)  
            conn.commit()
        except _m.ValidationError:
            conn.rollback()
            raise
        finally:
            conn.close()
        return cls.get(record_id)

    @classmethod
    def dismiss(cls, record_id: int, admin_id: int, reason=None):
        """Rejects a report. The reason is required and is shown to the reporter."""
        reason = cls._clean_reason(reason)
        conn = _m.get_connection()
        try:
            cur, _resource, record = cls._lock_record(conn, record_id)
            if record["status"] != "Reported":
                raise _m.ValidationError(f"This report was already {record['status'].lower()}.")
            cur.execute(
                """UPDATE maintenance_records
                   SET status = 'Dismissed', dismiss_reason = %s, closed_by = %s, closed_at = NOW()
                   WHERE id = %s""",
                (reason, admin_id, record_id),
            )
            _m.events.maintenance_dismissed(conn, record_id, admin_id)   
            conn.commit()
        except _m.ValidationError:
            conn.rollback()
            raise
        finally:
            conn.close()
        return cls.get(record_id)
