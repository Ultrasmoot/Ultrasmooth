# eemaining SELECT handlers for the fake maintenance cursor.
import datetime


class FakeCursorSelectJoined:
    def _select_joined_sql(self, q, p):
        db = self.db
        if "from maintenance_records m join resources r" in q:
            rows = list(db.records.values())
            if "where m.id = %s" in q:
                rows = [r for r in rows if r["id"] == p[0]]
            else:
                if "m.reported_by = %s" in q:
                    owner = p.pop(0)
                    rows = [r for r in rows if r["reported_by"] == owner]
                if "m.status in" in q:
                    rows = [r for r in rows if r["status"] in p]
                rows.sort(key=lambda r: (r["created_at"], r["id"]), reverse=True)
            self._rows = [self._joined(r) for r in rows]
        elif q.startswith("select count(*) as n from bookings where resource_id"):
            self._rows = [{"n": getattr(db, "active_sessions", {}).get(p[0], 0)}]
        else:
            return False
        return True


class FakeCursorInsert:
    def _insert_sql(self, q, p):
        db = self.db
        if q.startswith("insert into maintenance_records"):
            rid = db._next
            db._next += 1
            db._clock += datetime.timedelta(minutes=1)
            if "confirmed_by" in q:  # admin report confirmed 
                res_id, by, desc, status, day, conf = p
                rec_status, confirmed_by, confirmed_at = status, conf, db._clock
            else:  # non admin report awaits admin 
                res_id, by, desc, day = p
                rec_status, confirmed_by, confirmed_at = "Reported", None, None
            db.records[rid] = {"id": rid, "resource_id": res_id, "reported_by": by, "description": desc,
                               "status": rec_status, "issue_date": day, "confirmed_by": confirmed_by,
                               "confirmed_at": confirmed_at, "closed_by": None, "closed_at": None,
                               "created_at": db._clock}
            self.lastrowid = rid
        else:
            return False
        return True