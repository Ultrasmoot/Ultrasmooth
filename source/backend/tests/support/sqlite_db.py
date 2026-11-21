import datetime
import os
import re
import sqlite3
import sys
import tempfile
import unittest 
from unittest import mock

import mysql.connector

from support import BACKEND 
from support.sqlite_schema import schema_statements, _now_text, _field, CursorSchemaStatementsNowText  
from support.sqlite_cursor_fetch import ConnectionFetchoneFetchall, CursorFetchoneFetchall, TestDatabaseFetchoneFetchall 
from support.sqlite_cursor import TestDatabaseCloseExecute

SCHEMA = os.path.join(BACKEND, "database", "schema.sql")

sqlite3.register_adapter(datetime.datetime, lambda d: d.isoformat(" "))
sqlite3.register_adapter(datetime.date, lambda d: d.isoformat())
sqlite3.register_converter("DATETIME", lambda b: datetime.datetime.fromisoformat(b.decode()))
sqlite3.register_converter("TIMESTAMP", lambda b: datetime.datetime.fromisoformat(b.decode()))
sqlite3.register_converter("DATE", lambda b: datetime.date.fromisoformat(b.decode()[:10]))

class Cursor(CursorSchemaStatementsNowText, CursorFetchoneFetchall):
    pass

class Connection(ConnectionFetchoneFetchall):
    pass

class TestDatabase(TestDatabaseFetchoneFetchall, TestDatabaseCloseExecute):
    """One SQLite file per test; get_connection() in every module is pointed at it."""

# -------------------------------------------------------------------------------------------- 
class DbTestCase(unittest.TestCase):
    """Base class with a fresh database, Flask app, and test users. 
    Provides user IDs and a helper to send requests as each user or anonymously"""

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

    def token(self, uid):
        from controllers.auth.controller import _issue_token
        from models.user.model import UserModel
        return _issue_token(UserModel.find_by_id(uid))

    def call(self, method, path, uid=None, json=None):
        headers = {"Authorization": f"Bearer {self.token(uid)}"} if uid else {}
        return getattr(self.client, method)(path, json=json, headers=headers)
