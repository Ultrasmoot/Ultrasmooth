# fake maintenance cursor UPDATE handlers.
import datetime


class FakeCursorUpdate:
    def _update_sql(self, q, p):
        db = self.db
        if q.startswith("update resources set status = %s where id = %s"):
            db.resources[p[1]]["status"] = p[0]
        elif q.startswith("update resources set status = 'maintenance'"):
            db.resources[p[0]]["status"] = "Maintenance"
        elif q.startswith("update resources set status = 'available'"):
            db.resources[p[0]]["status"] = "Available"
        elif q.startswith("update resources set status=%s where id=%s and status <> 'maintenance'"):
            r = db.resources[p[1]]
            if r["status"] != "Maintenance":
                r["status"] = p[0]
                self.rowcount = 1
        elif q.startswith("update resources set name=%s"):
            r = db.resources[p[5]]
            r["name"], r["type"], r["category"], r["location"], r["owner"] = p[:5]
        elif q.startswith("update maintenance_records set status = 'open'"):
            r = db.records[p[1]]
            r.update(status="Open", confirmed_by=p[0], confirmed_at=db._clock)
        elif q.startswith("update maintenance_records set status = 'dismissed'"):
            db.records[p[2]].update(status="Dismissed", dismiss_reason=p[0], closed_by=p[1], closed_at=db._clock)
        elif q.startswith("update maintenance_records set status = 'resolved'") and "where resource_id" in q:
            closed_by, resource_id = p
            for r in db.records.values():
                if r["resource_id"] == resource_id and r["status"] in ("Open", "In Progress"):
                    r.update(status="Resolved", closed_by=closed_by, closed_at=db._clock)
                    self.rowcount += 1
        elif q.startswith("update maintenance_records set status = 'resolved'"):
            db.records[p[1]].update(status="Resolved", closed_by=p[0], closed_at=db._clock)
        elif q.startswith("update resources set is_archived = 0 where id"):
            db.resources[p[0]]["is_archived"] = 0
        elif q.startswith("update maintenance_records set description=%s, status=%s, issue_date=%s"):
            db.records[p[3]].update(description=p[0], status=p[1], issue_date=p[2])
        else:
            return False
        return True