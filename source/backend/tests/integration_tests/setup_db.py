import re
import integration_tests.base as _m

def _statements(path):
    lines = [ln for ln in open(path, encoding="utf-8").read().splitlines() if not ln.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]

class RealMySQLTestsBaseStatementsSetupclass:
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
        for statement in _m._statements(_m.SCHEMA):
            cur.execute(statement)
        admin.commit()
        admin.close()

        cls._saved = {k: getattr(Config, k) for k in ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME")}
        Config.DB_HOST, Config.DB_PORT, Config.DB_USER = _m.DB_HOST, _m.DB_PORT, _m.DB_USER
        Config.DB_PASSWORD, Config.DB_NAME = _m.DB_PASSWORD, _m.DB_NAME
        cls._db_module = db_module
        db_module._pool = None  # rebuilt lazily with the test credentials

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
        self.mails = []
        patcher = _m.mock.patch(
            "controllers.auth.controller.send_email_in_background",
            side_effect=lambda to, subject, body, dev_log_line=None: self.mails.append((to, body)),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        for table in ("appointments", "professor_profiles", "notifications", "activity_log",   # Iteration 5
                      "checkin_codes", "password_resets", "email_verifications", "maintenance_records",
                      "bookings", "announcements", "resources", "users"):
            self.sql(f"DELETE FROM {table}")

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

    def signup(self, email="alice@ku.th", password="OldPassword1", student_id="6512345678"):
        r = self.client.post("/api/auth/signup", json={
            "role": "undergrad_student", "student_id": student_id, "full_name": "Alice", "email": email,
            "password": password, "year": 2})
        self.assertEqual(r.status_code, 201, r.get_json())
        self.assertNotIn("token", r.get_json())  # no session until the email is verified
        # Sign-up now needs the emailed link; open it, then log in.
        link_token = re.search(r"verify_token=([\w-]+)", self.mails[-1][1]).group(1)
        self.assertEqual(
            self.client.post("/api/auth/verify-email", json={"token": link_token}).status_code, 200)
        self.mails.clear()
        login = self.client.post("/api/auth/login", json={"email": email, "password": password})
        self.assertEqual(login.status_code, 200, login.get_json())
        return login.get_json()["token"], login.get_json()["user"]["id"]

    def auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    def ping(self, token):
        return self.client.get("/api/me/ping", headers=self.auth(token)).status_code
