import importlib.util
import os
import sys

# backend/ folder; putting it on sys.path lets the tests import app, models, controllers, ...
BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

# sqlite_db <-> sqlite_schema import each other, and sqlite_schema reads sqlite_db.SCHEMA
# while sqlite_db is still loading. Load sqlite_db here with SCHEMA already set so that works.
_name = __name__ + ".sqlite_db"
if _name not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_name, os.path.join(os.path.dirname(__file__), "sqlite_db.py"))
    _mod = importlib.util.module_from_spec(_spec)
    _mod.SCHEMA = os.path.join(BACKEND, "database", "schema.sql")
    sys.modules[_name] = _mod
    try:
        _spec.loader.exec_module(_mod)
    except BaseException:
        sys.modules.pop(_name, None)
        raise
    sqlite_db = _mod
