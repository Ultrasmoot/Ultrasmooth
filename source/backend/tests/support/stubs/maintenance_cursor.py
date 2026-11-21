from support.stubs.maintenance_sql import FakeCursorSelectBasic, _norm
from support.stubs.maintenance_sql_joined import FakeCursorSelectJoined
from support.stubs.maintenance_sql_joined import FakeCursorInsert
from support.stubs.maintenance_sql_write import FakeCursorUpdate


class FakeCursor(FakeCursorSelectBasic, FakeCursorSelectJoined, FakeCursorInsert, FakeCursorUpdate):
    def __init__(self, db):
        self.db = db
        self._rows = []
        self.lastrowid = None
        self.rowcount = 0

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def _joined(self, rec):
        out = dict(rec)
        out["resource_name"] = self.db.resources[rec["resource_id"]]["name"]
        out["resource_code"] = self.db.resources[rec["resource_id"]]["resource_code"]
        out["reporter_name"] = self.db.users[rec["reported_by"]]["full_name"]
        out["reporter_email"] = self.db.users[rec["reported_by"]]["email"]
        return out

    def _select_sql(self, q, p):
        return self._select_basic_sql(q, p) or self._select_joined_sql(q, p)

    def execute(self, sql, params=()):
        q, p = _norm(sql), list(params or ())
        self._rows, self.rowcount = [], 0
        # MySQL resets lastrowid to 0 after non INSERT statements
        if not q.startswith("insert"):
            self.lastrowid = 0
        if not (self._select_sql(q, p) or self._insert_sql(q, p) or self._update_sql(q, p)):
            raise AssertionError(f"FakeDB does not understand SQL: {q}")