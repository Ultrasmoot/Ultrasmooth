import datetime
import os
import sys
import unittest

os.environ.setdefault("APP_ENV", "development")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_HOST = os.getenv("VASE_TEST_DB_HOST")
DB_PORT = int(os.getenv("VASE_TEST_DB_PORT", "3306"))
DB_USER = os.getenv("VASE_TEST_DB_USER", "root")
DB_PASSWORD = os.getenv("VASE_TEST_DB_PASSWORD", "")
DB_NAME = os.getenv("VASE_TEST_DB_NAME", "vase_test")
SCHEMA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database", "schema.sql")
DAY = datetime.timedelta(days=1)


def _statements(path):
    lines = [ln for ln in open(path, encoding="utf-8").read().splitlines() if not ln.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


@unittest.skipUnless(DB_HOST, "set VASE_TEST_DB_HOST to run the real-MySQL integration tests")
class FeaturesRealMySQLTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not DB_NAME.endswith("_test"):
            raise RuntimeError(f"Refusing to wipe database {DB_NAME!r}: its name must end with '_test'.")
        import mysql.connector

        from config import Config
        from database import db as db_module

        admin = mysql.connector.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD)
        cur = admin.cursor()
        cur.execute(f"DROP DATABASE IF EXISTS `{DB_NAME}`")
        cur.execute(f"CREATE DATABASE `{DB_NAME}` CHARACTER SET utf8mb4")
        cur.execute(f"USE `{DB_NAME}`")
        for statement in _statements(SCHEMA):    
            cur.execute(statement)
        admin.commit()
        admin.close()
        cls._saved = {k: getattr(Config, k) for k in ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME")}
        Config.DB_HOST, Config.DB_PORT, Config.DB_USER = DB_HOST, DB_PORT, DB_USER
        Config.DB_PASSWORD, Config.DB_NAME = DB_PASSWORD, DB_NAME
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

        conn = mysql.connector.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
                                       database=DB_NAME, autocommit=True)
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
        from controllers.auth_controller import _issue_token
        from models.user_model import UserModel

        headers = {"Authorization": f"Bearer {_issue_token(UserModel.find_by_id(uid))}"}
        return getattr(self.client, method)(path, json=json, headers=headers)

    def when(self, days, hour):
        return (datetime.datetime.now() + days * DAY).replace(hour=hour, minute=0, second=0, microsecond=0)

    # tests
    def test_booking_flow_writes_the_log_and_the_notifications_in_one_go(self):
        rid = self.call("post", "/api/resources", self.admin, {"name": "3D Printer", "type": "Equipment",
                        "category": "Fabrication", "location": "Lab", "owner": "Admin"}).get_json()["resource"]["id"]
        start = self.when(2, 10)
        r = self.call("post", "/api/bookings", self.student, {"resource_id": rid, "start_time": start.isoformat(),
                      "end_time": (start + datetime.timedelta(hours=2)).isoformat(), "purpose": "Print"})
        self.assertEqual(r.status_code, 201, r.get_json())
        bid = r.get_json()["booking"]["id"]
        self.assertEqual(self.call("post", f"/api/bookings/{bid}/decide", self.admin,
                                   {"decision": "reject", "reason": "Class that day"}).status_code, 200)
        log = self.call("get", "/api/activity?per_page=5&page=1", self.professor).get_json()
        self.assertEqual([i["action"] for i in log["items"]], ["booking.rejected", "booking.submitted", "resource.created"])
        self.assertEqual(len(self.call("get", f"/api/activity?user={self.student}", self.admin).get_json()["items"]), 1)
        mine = self.call("get", "/api/notifications", self.student).get_json()
        self.assertEqual((mine["unread"], mine["notifications"][0]["title"]), (1, "Booking declined"))
        self.assertEqual(self.call("get", "/api/notifications", self.admin).get_json()["notifications"][0]["title"], "New booking request")

    def test_dashboard_and_resource_detail_queries_run_on_mysql(self):
        rid = self.call("post", "/api/resources", self.admin, {"name": "Laser Cutter", "type": "Equipment",
                        "category": "Fabrication", "location": "Lab", "owner": "Admin"}).get_json()["resource"]["id"]
        now = datetime.datetime.now()
        self.sql("INSERT INTO bookings (resource_id, requester_id, start_time, end_time, purpose, status) "
                 "VALUES (%s, %s, %s, %s, 'Cut', 'Approved')", (rid, self.student, now - datetime.timedelta(hours=1), now + datetime.timedelta(hours=1)))
        dash = self.call("get", "/api/dashboard?days=7", self.professor).get_json()
        self.assertEqual((dash["resources"]["total"], dash["bookings"]["active"]), (1, 1))
        self.assertEqual(dash["utilization"][0]["category"], "Fabrication")
        self.assertEqual(self.call("get", "/api/dashboard", self.student).status_code, 403)
        detail = self.call("get", f"/api/resources/{rid}/detail", self.admin).get_json()
        self.assertEqual(detail["schedule"][0]["requester_name"], "Demo Student")
        self.assertEqual(self.call("get", f"/api/resources/{rid}/detail", self.student).get_json()["schedule"][0].keys(),
                         {"start_time", "end_time"})

    def test_demo_seed_loads(self):
        """seed.sql is MySQL, so this is the only place it can be checked."""
        import mysql.connector

        lines = [ln for ln in open(os.path.join(os.path.dirname(SCHEMA), "seed.sql"), encoding="utf-8").read().splitlines()
                 if not ln.strip().startswith("--")]
        conn = mysql.connector.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
                                       database=DB_NAME, autocommit=True)
        try:
            cur = conn.cursor()
            for statement in [s.strip() for s in "\n".join(lines).split(";") if s.strip()]:
                cur.execute(statement)
        finally:
            conn.close()
        professors = self.call("get", "/api/appointments/professors", self.sql(
            "SELECT id FROM users WHERE email = 'student@ku.th'", fetch=True)[0]["id"]).get_json()["professors"]
        self.assertGreaterEqual(len(professors), 5)
        self.assertTrue(all(p["expertise"] for p in professors))
        self.assertGreaterEqual(self.sql("SELECT COUNT(*) AS n FROM activity_log", fetch=True)[0]["n"], 7)


if __name__ == "__main__":
    unittest.main()
