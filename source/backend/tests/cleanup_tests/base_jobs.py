# shared lock cancellation, logged mail failures
import datetime
import os
import sys
from unittest import mock

import support  # noqa: F401,E402

from support.sqlite_db import DbTestCase  # noqa: E402

H = datetime.timedelta(hours=1)


class StrictCursor:
    """Mimics MySQL cursor errors when a result is unread."""

    def __init__(self, inner):
        self._inner, self._unread = inner, False

    def execute(self, sql, params=()):
        if self._unread:
            raise RuntimeError("Unread result found")
        self._inner.execute(sql, params)
        self._unread = sql.lstrip().lower().startswith("select")

    def fetchone(self):
        self._unread = False
        return self._inner.fetchone()

    def fetchall(self):
        self._unread = False
        return self._inner.fetchall()

    def __getattr__(self, name):
        return getattr(self._inner, name)