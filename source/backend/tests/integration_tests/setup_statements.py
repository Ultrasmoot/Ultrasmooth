import integration_tests.base_features as _m
import datetime

def _statements(path):
    lines = [ln for ln in open(path, encoding="utf-8").read().splitlines() if not ln.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]

class FeaturesRealMySQLTestsBaseStatementsSetupclass2:
    @classmethod
    def setUpClass(cls):
        if not _m.DB_NAME.endswith("_test"):
            raise RuntimeError(f"Refusing to wipe database {_m.DB_NAME!r}: its name must end with '_test'.")
        import mysql.connector

        from config import Config
        from database import db as db_module

        admin = mysql.connector.connect(host=_m.DB_HOST, port=_m.DB_PORT, user=_m.DB_USER, password=_m.DB_PASSWORD)
        cur = admin.cursor()
        cur.execute(f"DROP DATABASE IF EXISTS `{_m.DB_NAME}`")
        cur.execute(f"CREATE DATABASE `{_m.DB_NAME}` CHARACTER SET utf8mb4")
        cur.execute(f"USE `{_m.DB_NAME}`")
        for statement in _m._statements(_m.SCHEMA): # also proves the new tables/columns are valid MySQL
            cur.execute(statement)
        admin.commit()
        admin.close()
        cls._saved = {k: getattr(Config, k) for k in ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME")}
        Config.DB_HOST, Config.DB_PORT, Config.DB_USER = _m.DB_HOST, _m.DB_PORT, _m.DB_USER
        Config.DB_PASSWORD, Config.DB_NAME = _m.DB_PASSWORD, _m.DB_NAME
        cls._db_module = db_module
        db_module._pool = None

    @classmethod
    def tearDownClass(cls):
        from config import Config

        for key, value in cls._saved.items():
            setattr(Config, key, value)
        cls._db_module._pool = None

    def setUp(self):
        from app import create_app
        from middleware.rate_limit import reset_rate_limits

        reset_rate_limits()
        self.client = create_app().test_client()
        for table in ("appointments", "professor_profiles", "notifications", "activity_log", "checkin_codes",
                      "password_resets", "email_verifications", "maintenance_records", "bookings",
                      "announcements", "resources", "users"):
            self.sql(f"DELETE FROM {table}")
        self.admin = self.user("admin", "Demo Admin", "admin@ku.th")
        self.professor = self.user("professor", "Prof Somchai", "somchai@ku.th")
        self.student = self.user("undergrad_student", "Demo Student", "student@ku.th")
        self.sql("INSERT INTO professor_profiles (user_id, expertise, bio) VALUES (%s, %s, %s)",
                 (self.professor, "Software testing,Requirements engineering", "Test automation"))

    # helpers
    def sql(self, statement, params=(), fetch=False):
        import mysql.connector

        conn = mysql.connector.connect(host=_m.DB_HOST, port=_m.DB_PORT, user=_m.DB_USER, password=_m.DB_PASSWORD,
                                       database=_m.DB_NAME, autocommit=True)
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(statement, params)
            return cur.fetchall() if fetch else cur.lastrowid
        finally:
            conn.close()

    def user(self, role, name, email):
        return self.sql(
            "INSERT INTO users (full_name, email, password_hash, role, year, is_active, email_verified) "
            "VALUES (%s, %s, 'x', %s, %s, 1, 1)", (name, email, role, 2 if role == "undergrad_student" else None))

    def call(self, method, path, uid, json=None):
        from controllers.auth.controller import _issue_token
        from models.user.model import UserModel

        headers = {"Authorization": f"Bearer {_issue_token(UserModel.find_by_id(uid))}"}
        return getattr(self.client, method)(path, json=json, headers=headers)


class FeaturesRealMySQLTestsBaseWhen:
    def when(self, days, hour):
        return (datetime.datetime.now() + days * _m.DAY).replace(hour=hour, minute=0, second=0, microsecond=0)
