import datetime
import hashlib
import os
import re
import sys
import unittest
from unittest import mock

os.environ.setdefault("APP_ENV", "development")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_HOST = os.getenv("VASE_TEST_DB_HOST")
DB_PORT = int(os.getenv("VASE_TEST_DB_PORT", "3306"))
DB_USER = os.getenv("VASE_TEST_DB_USER", "root")
DB_PASSWORD = os.getenv("VASE_TEST_DB_PASSWORD", "")
DB_NAME = os.getenv("VASE_TEST_DB_NAME", "vase_test")

VERIFY = "controllers.auth_controller.id_token.verify_oauth2_token"
SCHEMA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database", "schema.sql")
MIN = datetime.timedelta(minutes=1)


def _statements(path):
    """Split schema SQL into statements after removing comment lines."""
    lines = [ln for ln in open(path, encoding="utf-8").read().splitlines() if not ln.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


@unittest.skipUnless(DB_HOST, "Set VASE_TEST_DB_HOST to run these integration tests")
class RealMySQLTests(unittest.TestCase):

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
        db_module._pool = None  # Recreate the pool with test credentials.

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
        patcher = mock.patch(
            "controllers.auth_controller.send_email_in_background",
            side_effect=lambda to, subject, body, dev_log_line=None: self.mails.append((to, body)),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        for table in ("checkin_codes", "password_resets", "email_verifications", "maintenance_records",
                      "bookings", "announcements", "resources", "users"):
            self.sql(f"DELETE FROM {table}")

    # Helpers
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

    def signup(self, email="alice@ku.th", password="OldPassword1", student_id="6512345678"):
        r = self.client.post("/api/auth/signup", json={
            "role": "undergrad_student", "student_id": student_id, "full_name": "Alice", "email": email,
            "password": password, "year": 2})
        self.assertEqual(r.status_code, 201, r.get_json())
        self.assertNotIn("token", r.get_json())  # No session before email verification.
        # Verify the email link before logging in.
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

    def request_reset(self, email="alice@ku.th"):
        from middleware.rate_limit import reset_rate_limits

        reset_rate_limits()
        before = len(self.mails)
        r = self.client.post("/api/auth/forgot-password", json={"email": email})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(self.mails), before + 1, "no reset e-mail was produced")
        return re.search(r"reset_token=([\w-]+)", self.mails[-1][1]).group(1)

    def reset(self, token, password):
        return self.client.post("/api/auth/reset-password", json={"token": token, "password": password})

    def login(self, password, email="alice@ku.th"):
        return self.client.post("/api/auth/login", json={"email": email, "password": password})

    # Password reset token tests
    def test_reset_token_is_stored_as_a_hash_and_works_exactly_once(self):
        old_jwt, user_id = self.signup()
        token = self.request_reset()

        rows = self.sql("SELECT token, used FROM password_resets WHERE user_id = %s", (user_id,), fetch=True)
        self.assertEqual(len(rows), 1)
        self.assertNotEqual(rows[0]["token"], token)                                   # Token is stored as a hash.
        self.assertEqual(rows[0]["token"], hashlib.sha256(token.encode()).hexdigest())
        self.assertEqual(rows[0]["used"], 0)

        self.assertEqual(self.reset("not-a-real-token", "NewPassword1").status_code, 400)
        self.assertEqual(self.reset(token, "short").status_code, 400)                  # Invalid input must not consume the link.
        self.assertEqual(self.sql("SELECT used FROM password_resets", fetch=True)[0]["used"], 0)

        self.assertEqual(self.reset(token, "NewPassword1").status_code, 200)
        self.assertEqual(self.sql("SELECT used FROM password_resets", fetch=True)[0]["used"], 1)
        self.assertEqual(self.login("NewPassword1").status_code, 200)
        self.assertEqual(self.login("OldPassword1").status_code, 401)
        self.assertEqual(self.reset(token, "AnotherPass1").status_code, 400)           # The link can only be used once.
        self.assertEqual(self.login("NewPassword1").status_code, 200)                  # The new password still works.

    def test_expired_reset_token_is_refused(self):
        self.signup()
        token = self.request_reset()
        self.sql("UPDATE password_resets SET expires_at = %s",
                 (datetime.datetime.utcnow() - 2 * MIN,))
        r = self.reset(token, "NewPassword1")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.login("OldPassword1").status_code, 200)

    def test_requesting_a_new_link_retires_the_previous_one(self):
        self.signup()
        first = self.request_reset()
        second = self.request_reset()
        self.assertEqual(self.reset(first, "NewPassword1").status_code, 400)
        self.assertEqual(self.reset(second, "NewPassword1").status_code, 200)

    def test_unknown_and_deactivated_accounts_get_the_same_answer_and_no_token(self):
        _, user_id = self.signup()
        self.sql("UPDATE users SET is_active = 0 WHERE id = %s", (user_id,))
        from middleware.rate_limit import reset_rate_limits

        for email in ("nobody@ku.th", "alice@ku.th"):
            reset_rate_limits()
            r = self.client.post("/api/auth/forgot-password", json={"email": email})
            self.assertEqual(r.status_code, 200)
            self.assertIn("If an account exists", r.get_json()["message"])
        self.assertEqual(self.mails, [])
        self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM password_resets", fetch=True)[0]["n"], 0)

    # Token revocation after password reset
    def test_jwt_issued_before_a_reset_stops_working_and_a_new_one_works(self):
        old_jwt, _ = self.signup()
        self.assertEqual(self.ping(old_jwt), 200)
        self.assertEqual(self.reset(self.request_reset(), "NewPassword1").status_code, 200)
        self.assertEqual(self.ping(old_jwt), 401)
        new_jwt = self.login("NewPassword1").get_json()["token"]
        self.assertEqual(self.ping(new_jwt), 200)

    # Google account linking tests
    def google(self, sub, email="alice@ku.th"):
        payload = {"sub": sub, "email": email, "email_verified": True, "name": "Alice"}
        with mock.patch(VERIFY, return_value=payload):
            return self.client.post("/api/auth/google", json={"credential": "tok"})

    def test_google_link_clears_the_password_revokes_old_tokens_and_cannot_be_replaced(self):
        old_jwt, user_id = self.signup()
        r = self.google("g-FIRST")
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(r.get_json()["user"]["id"], user_id)
        row = self.sql("SELECT google_sub, password_hash FROM users WHERE id = %s", (user_id,), fetch=True)[0]
        self.assertEqual(row["google_sub"], "g-FIRST")
        self.assertIsNone(row["password_hash"])
        self.assertEqual(self.ping(old_jwt), 401)                          # Old password token is revoked.
        self.assertEqual(self.login("OldPassword1").status_code, 401)

        # Another Google account with the same email cannot take over this account.
        other = self.google("g-SOMEONE-ELSE")
        self.assertEqual(other.status_code, 403)
        self.assertNotIn("token", other.get_json())
        self.assertEqual(self.sql("SELECT google_sub FROM users WHERE id = %s", (user_id,), fetch=True)[0]["google_sub"],
                         "g-FIRST")
        self.assertEqual(self.google("g-FIRST").status_code, 200)         # The linked Google account still works.

    def test_google_sign_in_does_not_touch_a_deactivated_account(self):
        _, user_id = self.signup()
        self.sql("UPDATE users SET is_active = 0 WHERE id = %s", (user_id,))
        self.assertEqual(self.google("g-FIRST").status_code, 403)
        row = self.sql("SELECT google_sub, password_hash FROM users WHERE id = %s", (user_id,), fetch=True)[0]
        self.assertIsNone(row["google_sub"])
        self.assertIsNotNone(row["password_hash"])

    def test_new_google_user_completes_sign_up_with_a_student_role(self):
        r = self.google("g-NEW", email="newbie@ku.th")
        self.assertEqual((r.status_code, r.get_json().get("needs_role")), (200, True))
        with mock.patch(VERIFY, return_value={"sub": "g-NEW", "email": "newbie@ku.th",
                                                "email_verified": True, "name": "Newbie"}):
            done = self.client.post("/api/auth/google/complete-profile",
                                    json={"credential": "tok", "role": "phd_student"})
        self.assertEqual(done.status_code, 201, done.get_json())
        self.assertEqual(self.sql("SELECT role FROM users WHERE email = 'newbie@ku.th'", fetch=True)[0]["role"],
                         "phd_student")

    # Booking and archive tests using real MySQL
    def _resource(self, status="Available", code="RES-0001"):
        return self.sql(
            "INSERT INTO resources (resource_code, name, type, category, location, owner, status) "
            "VALUES (%s, 'Printer', 'Equipment', 'Fab', 'Lab A', 'Admin', %s)", (code, status))

    def _booking(self, rid, uid, start, end, status="Approved", checked_in=None, checked_out=None):
        return self.sql(
            "INSERT INTO bookings (resource_id, requester_id, start_time, end_time, purpose, status, "
            "checked_in_at, checked_out_at) VALUES (%s, %s, %s, %s, 'x', %s, %s, %s)",
            (rid, uid, start, end, status, checked_in, checked_out))

    def _create(self, rid, uid, start, hours=1):
        from models.booking_model import BookingModel

        return BookingModel.create({"resource_id": rid, "start_time": start.isoformat(),
                                    "end_time": (start + datetime.timedelta(hours=hours)).isoformat(),
                                    "purpose": "Test"}, requester_id=uid)

    def test_in_use_booking_rules_and_archive_on_real_mysql(self):
        from models.booking_model import ValidationError as BookingError
        from models.resource_model import ResourceModel, ValidationError as ResourceError

        _, student = self.signup()
        _, other = self.signup(email="bob@ku.th", student_id="6512345679")
        now = datetime.datetime.now().replace(microsecond=0)
        rid = self._resource(status="In Use")
        busy = self._booking(rid, other, now - 120 * MIN, now + 120 * MIN, checked_in=now - 100 * MIN)

        with self.assertRaises(BookingError) as ctx:                       # Overlaps the current booking.
            self._create(rid, student, now + 60 * MIN)
        self.assertIn("in use until", str(ctx.exception))
        self.assertEqual(self._create(rid, student, now + 120 * MIN)["status"], "Pending")  # Starts when the current booking ends.

        with self.assertRaises(ResourceError) as ctx:                      # Resources in use cannot be archived.
            ResourceModel.archive(rid)
        self.assertIn("In Use", str(ctx.exception))

        # Checkout frees the resource, but active bookings still block archiving.
        self.sql("UPDATE bookings SET checked_out_at = %s WHERE id = %s", (now, busy))
        self.sql("UPDATE resources SET status = 'Available' WHERE id = %s", (rid,))
        with self.assertRaises(ResourceError) as ctx:
            ResourceModel.archive(rid)
        self.assertIn("active bookings", str(ctx.exception))

        # Reject the pending request and move the old booking well into the past. The one-day gap
        # avoids relying on the database and app clocks having the same time zone.
        self.sql("UPDATE bookings SET status = 'Rejected' WHERE status = 'Pending'")
        self.sql("UPDATE bookings SET start_time = %s, end_time = %s WHERE id = %s",
                 (now - 48 * 60 * MIN, now - 24 * 60 * MIN, busy))
        ResourceModel.archive(rid)
        self.assertEqual(self.sql("SELECT is_archived FROM resources WHERE id = %s", (rid,), fetch=True)[0]["is_archived"], 1)

    def test_demo_seed_loads_and_is_consistent(self):
        """Check seed data and ensure In Use resources have a checked-in booking."""
        import mysql.connector

        seed = os.path.join(os.path.dirname(SCHEMA), "seed.sql")
        conn = mysql.connector.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
                                       database=DB_NAME, autocommit=True)
        try:
            cur = conn.cursor()
            for statement in _statements(seed):
                cur.execute(statement)
        finally:
            conn.close()
        orphans = self.sql(
            """SELECT r.resource_code FROM resources r
               WHERE r.status = 'In Use' AND NOT EXISTS (
                   SELECT 1 FROM bookings b WHERE b.resource_id = r.id AND b.status = 'Approved'
                     AND b.checked_in_at IS NOT NULL AND b.checked_out_at IS NULL)""", fetch=True)
        self.assertEqual(orphans, [], "a resource is In Use without a checked-in booking")
        # No demo booking is checked in initially, so resources start Available
        # except RES-0004, which is under maintenance.
        self.assertEqual(self.sql("SELECT status FROM resources WHERE resource_code = 'RES-0002'", fetch=True)[0]["status"],
                         "Available")
        # RES-0001 has an active approved booking that has not been checked in.
        demo = self.sql(
            """SELECT b.status, b.checked_in_at FROM bookings b JOIN resources r ON r.id = b.resource_id
               WHERE r.resource_code = 'RES-0001' AND b.status = 'Approved'
                 AND b.start_time <= NOW() AND b.end_time > NOW()""", fetch=True)
        self.assertEqual(len(demo), 1)
        self.assertIsNone(demo[0]["checked_in_at"])
        self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM bookings WHERE status = 'Pending' AND start_time > NOW()",
                                  fetch=True)[0]["n"], 1)


if __name__ == "__main__":
    unittest.main()
