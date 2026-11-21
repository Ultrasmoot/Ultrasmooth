import os
import sqlite3
import sys
import tempfile
import support.sqlite_db as _m

class CursorFetchoneFetchall:
    def fetchone(self):
        return self._row(self._raw.fetchone())

    def fetchall(self):
        return [self._row(r) for r in self._raw.fetchall()]

    @property
    def rowcount(self):
        return self._raw.rowcount

    @property
    def lastrowid(self):
        return self._raw.lastrowid

    @property
    def description(self):
        return self._raw.description


class ConnectionFetchoneFetchall:
    def __init__(self, path):
        self._c = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES, timeout=5)
        self._c.create_function("NOW", 0, _m._now_text)
        self._c.create_function("FIELD", -1, _m._field)

    def cursor(self, dictionary=False, buffered=False, **_):
        return _m.Cursor(self._c.cursor(), dictionary)

    def commit(self):
        self._c.commit()

    def rollback(self):
        self._c.rollback()

    def close(self):
        self._c.close()


class TestDatabaseFetchoneFetchall:
    def __init__(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "test.db")
        conn = _m.Connection(self.path)
        cur = conn.cursor()
        for stmt in _m.schema_statements():
            cur.execute(stmt.replace("%", "%%") if False else stmt)
        conn.commit()
        conn.close()
        self._patches = []

    def connect(self):
        return _m.Connection(self.path)

    def install(self):
        """Patch get_connection everywhere it was imported by name."""
        import database.db as dbmod
        targets = [dbmod] + [m for n, m in list(sys.modules.items())
                             if m is not None and n.split(".")[0] in ("models", "services", "controllers", "middleware")
                             and hasattr(m, "get_connection")]
        for module in targets:
            p = _m.mock.patch.object(module, "get_connection", side_effect=self.connect)
            p.start()
            self._patches.append(p)
