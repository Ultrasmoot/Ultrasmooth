import datetime
import os
import re
import sqlite3
import sys
import tempfile
from unittest import mock

import mysql.connector

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(BACKEND, "database", "schema.sql")

# Register SQLite adapters and converters for date and time values.
sqlite3.register_adapter(datetime.datetime, lambda d: d.isoformat(" "))
sqlite3.register_adapter(datetime.date, lambda d: d.isoformat())
sqlite3.register_converter("DATETIME", lambda b: datetime.datetime.fromisoformat(b.decode()))
sqlite3.register_converter("TIMESTAMP", lambda b: datetime.datetime.fromisoformat(b.decode()))
sqlite3.register_converter("DATE", lambda b: datetime.date.fromisoformat(b.decode()[:10]))


# Convert MySQL schema statements to SQLite syntax.
def schema_statements(path=SCHEMA):
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    text = "\n".join(ln for ln in lines if not ln.strip().startswith("--"))
    text = re.sub(r"\b(?:BIGINT|INT)\s+AUTO_INCREMENT\s+PRIMARY\s+KEY", "INTEGER PRIMARY KEY AUTOINCREMENT", text, flags=re.I)
    text = re.sub(r"^\s*(?:UNIQUE\s+)?(?:INDEX|KEY)\s+\w+\s*\([^)]*\)\s*,?\s*$", "", text, flags=re.I | re.M)
    text = re.sub(r"ENUM\s*\([^)]*\)", "TEXT", text, flags=re.I)
    text = re.sub(r"\bUNSIGNED\b", "", text, flags=re.I)
    text = re.sub(r"ON\s+UPDATE\s+CURRENT_TIMESTAMP", "", text, flags=re.I)
    text = re.sub(r",(\s*\))", r"\1", text)
    return [s.strip() for s in text.split(";") if s.strip()]


# Return the current date and time as text.
def _now_text():
    return datetime.datetime.now().isoformat(" ")


# Return the 1-based position of a value in the options.
def _field(value, *options):
    try:
        return options.index(value) + 1
    except ValueError:
        return 0


# Wrap SQLite cursor methods to match MySQL behavior.
class Cursor:
    def __init__(self, raw, dictionary):
        self._raw, self._dict = raw, dictionary

    @staticmethod
    def _sql(sql):
        sql = re.sub(r"\s+FOR\s+UPDATE\b", "", sql, flags=re.I)
        return sql.replace("%s", "?")

    def _wrap(self, exc):
        if isinstance(exc, sqlite3.IntegrityError):
            return mysql.connector.IntegrityError(str(exc))
        return exc

    def execute(self, sql, params=()):
        try:
            self._raw.execute(self._sql(sql), tuple(params or ()))
        except sqlite3.IntegrityError as e:
            raise self._wrap(e)
        return self

    def executemany(self, sql, seq):
        try:
            self._raw.executemany(self._sql(sql), [tuple(p) for p in seq])
        except sqlite3.IntegrityError as e:
            raise self._wrap(e)

    def _row(self, row):
        if row is None or not self._dict:
            return row
        return {d[0]: v for d, v in zip(self._raw.description, row)}

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


# Provide a MySQL compatible SQLite connection for tests
class Connection:
    def __init__(self, path):
        self._c = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES, timeout=5)
        self._c.create_function("NOW", 0, _now_text)
        self._c.create_function("FIELD", -1, _field)

    def cursor(self, dictionary=False, buffered=False, **_):
        return Cursor(self._c.cursor(), dictionary)

    def commit(self):
        self._c.commit()

    def rollback(self):
        self._c.rollback()

    def close(self):
        self._c.close()


# Create an isolated SQLite database for each test
class TestDatabase:
    def __init__(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "test.db")
        conn = Connection(self.path)
        cur = conn.cursor()
        for stmt in schema_statements():
            cur.execute(stmt)
        conn.commit()
        conn.close()
        self._patches = []

    def connect(self):
        return Connection(self.path)

    # Replace module database connections with the test database
    def install(self):
        import database.db as dbmod
        targets = [dbmod] + [m for n, m in list(sys.modules.items())
                             if m is not None and n.split(".")[0] in ("models", "services", "controllers", "middleware")
                             and hasattr(m, "get_connection")]
        for module in targets:
            p = mock.patch.object(module, "get_connection", side_effect=self.connect)
            p.start()
            self._patches.append(p)

    def close(self):
        for p in self._patches:
            p.stop()
        self._patches = []
        self.dir.cleanup()

    # Create a test user
    def add_user(self, role, name, email=None, active=1):
        email = email or f"{name.lower().replace(' ', '.')}@ku.th"
        year = 3 if role == "undergrad_student" else None
        return self.execute(
            "INSERT INTO users (full_name, email, password_hash, role, year, is_active, email_verified) "
            "VALUES (%s, %s, %s, %s, %s, %s, 1)",
            (name, email, "x", role, year, active),
        )

    # Create a test resource
    def add_resource(self, name, category="Fabrication", status="Available", **extra):
        code = f"RES-{self.one('SELECT COUNT(*) AS n FROM resources')['n'] + 1:04d}"
        return self.execute(
            "INSERT INTO resources (resource_code, name, type, category, location, owner, status, is_archived) "
            "VALUES (%s, %s, 'Equipment', %s, 'Lab A', 'Admin', %s, %s)",
            (code, name, category, status, extra.get("archived", 0)),
        )

    # Create a test booking
    def add_booking(self, resource_id, user_id, start, end, status="Approved", purpose="Test", **extra):
        return self.execute(
            "INSERT INTO bookings (resource_id, requester_id, start_time, end_time, purpose, status, "
            "checked_in_at, checked_out_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (resource_id, user_id, start, end, purpose, status, extra.get("checked_in_at"), extra.get("checked_out_at")),
        )


import unittest  # noqa: E402


# Base test case with a fresh database and ready-made users
class DbTestCase(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("APP_ENV", "development")
        if BACKEND not in sys.path:
            sys.path.insert(0, BACKEND)
        from app import create_app
        from middleware.rate_limit import reset_rate_limits

        reset_rate_limits()
        self.db = TestDatabase()
        self.db.install()
        self.addCleanup(self.db.close)
        self.client = create_app().test_client()
        self.admin = self.db.add_user("admin", "Demo Admin", "admin@ku.th")
        self.professor = self.db.add_user("professor", "Prof Somchai", "somchai@ku.th")
        self.student = self.db.add_user("undergrad_student", "Demo Student", "student@ku.th")
        self.other = self.db.add_user("phd_student", "Other Student", "other@ku.th")

    # Generate an authentication token for a user
    def token(self, uid):
        from controllers.auth_controller import _issue_token
        from models.user_model import UserModel
        return _issue_token(UserModel.find_by_id(uid))

    # Send a request with an optional authenticated user
    def call(self, method, path, uid=None, json=None):
        headers = {"Authorization": f"Bearer {self.token(uid)}"} if uid else {}
        return getattr(self.client, method)(path, json=json, headers=headers)