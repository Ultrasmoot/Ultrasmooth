import datetime
import mysql.connector
import re
import sqlite3
import support.sqlite_db as _m

def schema_statements(path=_m.SCHEMA):
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

def _now_text():
    return datetime.datetime.now().isoformat(" ")

def _field(value, *options):
    try:
        return options.index(value) + 1
    except ValueError:
        return 0

class CursorSchemaStatementsNowText:
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
