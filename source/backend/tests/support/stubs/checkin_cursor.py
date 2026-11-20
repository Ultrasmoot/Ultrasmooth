from support.stubs.maintenance_cursor import FakeCursor
from support.stubs.checkin_sql_write import _norm
from support.stubs.checkin_sql import CurSelect
from support.stubs.checkin_sql_write import CurWrite


class Cur(CurSelect, CurWrite, FakeCursor):
    def _joined(self, b):
        r = self.db.resources[b["resource_id"]]
        return {**b, "resource_name": r["name"], "resource_code": r["resource_code"], "resource_status": r["status"]}

    def execute(self, sql, params=()):
        q, p = _norm(sql), list(params or ())
        if not q.startswith("insert"):
            self.lastrowid = 0  # MySQL only INSERT 
        if self._checkin_select_sql(q, p):
            return
        if self._checkin_write_sql(q, p):
            if not q.startswith("insert"):
                self._rows = []
            return
        self._rows, self.rowcount = [], 0
        return super().execute(sql, params)
