# The SQL the fake maintenance cursor understands, one handler per kind of statement
import datetime


def _norm(sql):
    return " ".join(sql.split()).lower()


class FakeCursorSelectBasic:
    def _select_basic_sql(self, q, p):
        db = self.db
        if q.startswith("select resource_id from maintenance_records where id"):
            r = db.records.get(p[0])
            self._rows = [{"resource_id": r["resource_id"]}] if r else []
        elif q.startswith("select id, status, is_archived from resources where id"):
            r = db.resources.get(p[0])
            self._rows = [{k: r[k] for k in ("id", "status", "is_archived")}] if r else []
        elif q.startswith("select status, is_archived from resources where id"):
            r = db.resources.get(p[0])
            self._rows = [{k: r[k] for k in ("status", "is_archived")}] if r else []
        elif q.startswith("select id, status from resources where id"):
            r = db.resources.get(p[0])
            self._rows = [{"id": r["id"], "status": r["status"]}] if r else []
        elif q.startswith("select * from resources where id"):
            r = db.resources.get(p[0])
            self._rows = [dict(r)] if r else []
        elif q.startswith("select * from maintenance_records where id"):
            r = db.records.get(p[0])
            self._rows = [dict(r)] if r else []
        elif q.startswith("select count(*) as n from maintenance_records"):
            exclude = p[1] if len(p) > 1 else None
            n = sum(1 for r in db.records.values()
                    if r["resource_id"] == p[0] and r["status"] in ("Open", "In Progress") and r["id"] != exclude)
            self._rows = [{"n": n}]
        else:
            return False
        return True
