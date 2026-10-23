import os
import sys
import config
import unittest
from unittest import mock

os.environ.setdefault("APP_ENV", "development")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from middleware.rate_limit import reset_rate_limits  # noqa: E402

VERIFY = "controllers.auth_controller.id_token.verify_oauth2_token"
GOOD = {"sub": "g-123", "email": "alice@ku.th", "email_verified": True, "name": "Alice"}
FAKE_USER = {"id": 7, "email": "alice@ku.th", "full_name": "Alice", "role": "undergrad_student"}

class GoogleAuthTests(unittest.TestCase):
    def setUp(self):
        reset_rate_limits()
        self.client = create_app().test_client()

    def test_complete_profile_rejects_unverified_body(self):
        # reject old attack using fake user data
        with mock.patch("controllers.auth_controller.UserModel") as um:
            r = self.client.post(
                "/api/auth/google/complete-profile",
                json={"google_sub": "evil", "email": "victim@ku.th", "role": "phd_student"},
            )
            self.assertEqual(r.status_code, 400)
            um.complete_google_signup.assert_not_called()

    def test_complete_profile_rejects_invalid_token(self):
        with mock.patch(VERIFY, side_effect=ValueError("bad")), mock.patch(
            "controllers.auth_controller.UserModel"
        ) as um:
            r = self.client.post(
                "/api/auth/google/complete-profile", json={"credential": "x", "role": "phd_student"}
            )
            self.assertEqual(r.status_code, 401)
            um.complete_google_signup.assert_not_called()

    def test_complete_profile_uses_token_identity_not_body(self):
        with mock.patch(VERIFY, return_value=GOOD), mock.patch(
            "controllers.auth_controller.UserModel"
        ) as um:
            um.complete_google_signup.return_value = FAKE_USER
            r = self.client.post(
                "/api/auth/google/complete-profile",
                json={
                    "credential": "tok",
                    "role": "undergrad_student",
                    "google_sub": "evil",
                    "email": "victim@ku.th",
                },
            )
            self.assertEqual(r.status_code, 201)
            um.complete_google_signup.assert_called_once_with(
                "g-123", "alice@ku.th", "Alice", "undergrad_student", year=None
            )
    def test_complete_profile_passes_year_to_model(self):
        with mock.patch(VERIFY, return_value=GOOD), mock.patch(
            "controllers.auth_controller.UserModel"
        ) as um:
            um.complete_google_signup.return_value = {**FAKE_USER, "year": 3}
            r = self.client.post(
                "/api/auth/google/complete-profile",
                json={"credential": "tok", "role": "undergrad_student", "year": 3},
            )
            self.assertEqual(r.status_code, 201)
            um.complete_google_signup.assert_called_once_with(
                "g-123", "alice@ku.th", "Alice", "undergrad_student", year=3
            )
            self.assertEqual(r.get_json()["user"]["year"], 3)

    def test_complete_profile_undergrad_without_year_is_400_and_creates_nothing(self):
        # Check invalid years are rejected before creating a database record.
        for body in ({}, {"year": None}, {"year": ""}, {"year": 0}, {"year": 7}, {"year": "abc"},
                     {"year": True}, {"year": 2.5}, {"year": [3]}):
            with mock.patch(VERIFY, return_value=GOOD), mock.patch(
                "models.user_model.get_connection"
            ) as gc:
                r = self.client.post(
                    "/api/auth/google/complete-profile",
                    json={"credential": "tok", "role": "undergrad_student", **body},
                )
                self.assertEqual(r.status_code, 400, body)
                gc.assert_not_called()

    def test_complete_profile_phd_does_not_need_year_and_stores_none(self):
        from models.user_model import UserModel
        conn = mock.MagicMock()
        conn.cursor.return_value.lastrowid = 9
        with mock.patch("models.user_model.get_connection", return_value=conn), \
             mock.patch.object(UserModel, "find_by_id", return_value=FAKE_USER):
            UserModel.complete_google_signup("g-1", "p@ku.th", "P", "phd_student", year=4)
        params = conn.cursor.return_value.execute.call_args[0][1]
        self.assertIsNone(params[-1])  # Ignore the year for Ph.D. students.

    def test_complete_profile_undergrad_year_is_stored_as_int(self):
        from models.user_model import UserModel
        conn = mock.MagicMock()
        conn.cursor.return_value.lastrowid = 9
        for given in (3, "3", " 3 "):
            with mock.patch("models.user_model.get_connection", return_value=conn), \
                 mock.patch.object(UserModel, "find_by_id", return_value=FAKE_USER):
                UserModel.complete_google_signup("g-1", "u@ku.th", "U", "undergrad_student", year=given)
            self.assertEqual(conn.cursor.return_value.execute.call_args[0][1][-1], 3)

    def test_complete_profile_rejects_wrong_domain_and_unverified_email(self):
        for payload in (
            {**GOOD, "email": "alice@gmail.com"},
            {**GOOD, "email_verified": False},
        ):
            with mock.patch(VERIFY, return_value=payload), mock.patch(
                "controllers.auth_controller.UserModel"
            ) as um:
                r = self.client.post(
                    "/api/auth/google/complete-profile",
                    json={"credential": "tok", "role": "phd_student"},
                )
                self.assertEqual(r.status_code, 403)
                um.complete_google_signup.assert_not_called()

    def test_google_login_does_not_leak_google_sub(self):
        with mock.patch(VERIFY, return_value=GOOD), mock.patch(
            "controllers.auth_controller.UserModel"
        ) as um:
            um.find_or_create_google_user.return_value = (None, True)
            r = self.client.post("/api/auth/google", json={"credential": "tok"})
            self.assertEqual(r.status_code, 200)
            self.assertNotIn("google_sub", r.get_json())

class RateLimitTests(unittest.TestCase):
    def setUp(self):
        reset_rate_limits()
        self.client = create_app().test_client()

    def test_login_is_limited_with_429(self):
        with mock.patch("controllers.auth_controller.UserModel") as um:
            um.authenticate.return_value = None
            codes = [
                self.client.post("/api/auth/login", json={"email": "a@ku.th", "password": "x"}).status_code
                for _ in range(12)
            ]
        self.assertEqual(codes[:10], [401] * 10)
        self.assertEqual(codes[10:], [429, 429])

    def test_forgot_and_reset_are_limited(self):
        with mock.patch("controllers.auth_controller.UserModel") as um:
            um.create_reset_token.return_value = None
            codes = [
                self.client.post("/api/auth/forgot-password", json={"email": "a@ku.th"}).status_code
                for _ in range(6)
            ]
            self.assertEqual(codes[-1], 429)
            codes = [
                self.client.post("/api/auth/reset-password", json={"token": ""}).status_code
                for _ in range(11)
            ]
            self.assertEqual(codes[-1], 429)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        reset_rate_limits()
        self.client = create_app().test_client()

    def _signup(self, **over):
        body = {"role": "undergrad_student", "student_id": "6512345678", "full_name": "A",
                "email": "a@ku.th", "password": "password123"}
        body.update(over)
        return self.client.post("/api/auth/signup", json=body)

    def test_signup_rejects_bad_input_without_500(self):
        with mock.patch("models.user_model.UserModel.find_by_email", return_value=None):
            for over in ({"password": "x" * 73}, {"password": 12345678}, {"full_name": ["a"]},
                         {"full_name": "n" * 151}, {"faculty": "f" * 151}, {"email": 5}):
                self.assertEqual(self._signup(**over).status_code, 400, over)

    def test_signup_undergrad_requires_valid_year(self):
        with mock.patch("models.user_model.UserModel.find_by_email", return_value=None):
            for bad in (None, "", 0, 7, "x", True):
                body = {} if bad is None else {"year": bad}
                self.assertEqual(self._signup(**body).status_code, 400, body)

    def test_signup_stores_year_for_undergrad_and_none_for_phd(self):
        from models.user_model import UserModel
        for role, given, expected in (("undergrad_student", 2, 2), ("phd_student", 2, None)):
            conn = mock.MagicMock()
            conn.cursor.return_value.lastrowid = 1
            with mock.patch("models.user_model.get_connection", return_value=conn), \
                 mock.patch.object(UserModel, "find_by_email", return_value=None), \
                 mock.patch.object(UserModel, "find_by_id", return_value=FAKE_USER):
                r = self._signup(role=role, year=given)
            self.assertEqual(r.status_code, 201, r.get_json())
            self.assertEqual(conn.cursor.return_value.execute.call_args_list[0][0][1][-1], expected)

    def test_signup_is_rate_limited(self):
        codes = [self._signup(role="admin").status_code for _ in range(11)]
        self.assertEqual(codes[:10], [400] * 10)
        self.assertEqual(codes[10], 429)

    def test_reset_rejects_long_password_before_touching_db(self):
        from models.user_model import UserModel, ValidationError
        with mock.patch("models.user_model.get_connection") as gc:
            with self.assertRaises(ValidationError):
                UserModel.reset_password("tok", "x" * 73)
            gc.assert_not_called()

    def test_reset_token_consumed_by_single_conditional_update(self):
        from models.user_model import UserModel, ValidationError
        conn = mock.MagicMock()
        cur = conn.cursor.return_value
        cur.rowcount = 0
        with mock.patch("models.user_model.get_connection", return_value=conn):
            with self.assertRaises(ValidationError):
                UserModel.reset_password("tok", "password123")
        conn.rollback.assert_called()
        conn.commit.assert_not_called()

        conn = mock.MagicMock()
        cur = conn.cursor.return_value
        cur.rowcount = 1
        cur.fetchone.return_value = {"user_id": 3}
        with mock.patch("models.user_model.get_connection", return_value=conn), \
             mock.patch.object(UserModel, "_hash_password", return_value="h"):
            UserModel.reset_password("tok", "password123")
        conn.commit.assert_called_once()

# Check that invalid JSON types, inactive accounts and Google outages are handled safely.
class WrongTypeTests(unittest.TestCase):
    def setUp(self):
        reset_rate_limits()
        self.client = create_app().test_client()

    def test_login_and_forgot_password_reject_non_text_values(self):
        with mock.patch("models.user_model.get_connection") as gc:
            for body in ({"email": 123, "password": "x"}, {"email": "a@ku.th", "password": 123},
                         {"email": ["a@ku.th"], "password": ["x"]}, {"email": {"a": 1}, "password": "x"}):
                reset_rate_limits()
                self.assertEqual(self.client.post("/api/auth/login", json=body).status_code, 400, body)
            for body in ({"email": 123}, {"email": ["a@ku.th"]}, {"email": {"a": 1}}):
                reset_rate_limits()
                self.assertEqual(self.client.post("/api/auth/forgot-password", json=body).status_code, 400, body)
            gc.assert_not_called()

    def test_body_that_is_not_a_json_object_is_a_400_on_every_api_route(self):
        for path in ("/api/auth/login", "/api/auth/signup", "/api/auth/forgot-password",
                     "/api/auth/reset-password", "/api/bookings", "/api/maintenance",
                     "/api/resources", "/api/announcements"):
            for body in ([1, 2], "text", 5, [{"a": 1}]):
                reset_rate_limits()
                r = self.client.post(path, json=body)
                self.assertEqual(r.status_code, 400, (path, body))
                self.assertEqual(r.get_json()["error"], "Request body must be a JSON object.")

    def test_complete_profile_role_must_be_text(self):
        with mock.patch(VERIFY, return_value=GOOD):
            for role in (["phd_student"], {"a": 1}, 5):
                r = self.client.post("/api/auth/google/complete-profile", json={"credential": "t", "role": role})
                self.assertEqual(r.status_code, 400, role)

    def test_password_check_never_raises(self):
        from models.user_model import UserModel
        good = UserModel._hash_password("password123")
        self.assertTrue(UserModel._check_password("password123", good))
        self.assertFalse(UserModel._check_password("x" * 100, good))          # Reject passwords over 72 bytes.
        self.assertFalse(UserModel._check_password(12345678, good))           # Reject non-text passwords.
        self.assertFalse(UserModel._check_password("password123", "garbage"))  # Handle invalid stored hashes.
        self.assertIsNone(UserModel.authenticate(123, "x"))
        self.assertIsNone(UserModel.authenticate("a@ku.th", ["x"]))

class GoogleDeactivatedAndOutageTests(unittest.TestCase):
    def setUp(self):
        reset_rate_limits()
        self.client = create_app().test_client()

    def test_google_sign_in_does_not_modify_a_deactivated_account(self):
        from models.user_model import UserModel
        inactive = {"id": 9, "email": "off@ku.th", "is_active": 0, "role": "phd_student",
                    "password_hash": "hash", "google_sub": None}
        with mock.patch.object(UserModel, "find_by_google_sub", return_value=None), \
             mock.patch.object(UserModel, "find_by_email", return_value=inactive), \
             mock.patch("models.user_model.get_connection") as gc:
            user, is_new = UserModel.find_or_create_google_user("g-1", "off@ku.th", "Off")
        self.assertEqual((user, is_new), (inactive, False))
        gc.assert_not_called()  # Do not link Google or change the password.

    def test_google_login_of_a_deactivated_account_is_403(self):
        inactive = {"id": 9, "email": "alice@ku.th", "is_active": 0, "role": "phd_student"}
        with mock.patch(VERIFY, return_value=GOOD), \
             mock.patch("controllers.auth_controller.UserModel") as um:
            um.find_or_create_google_user.return_value = (inactive, False)
            r = self.client.post("/api/auth/google", json={"credential": "t"})
        self.assertEqual(r.status_code, 403)
        self.assertNotIn("token", r.get_json())

    def test_google_certificate_outage_is_503_not_500(self):
        from google.auth.exceptions import TransportError
        with mock.patch(VERIFY, side_effect=TransportError("no network")):
            for path in ("/api/auth/google", "/api/auth/google/complete-profile"):
                r = self.client.post(path, json={"credential": "t", "role": "phd_student"})
                self.assertEqual(r.status_code, 503, path)

    def test_verifier_is_called_with_clock_skew(self):
        with mock.patch(VERIFY, return_value=GOOD) as v, \
             mock.patch("controllers.auth_controller.UserModel") as um:
            um.find_or_create_google_user.return_value = (None, True)
            self.client.post("/api/auth/google", json={"credential": "t"})
        self.assertEqual(v.call_args.kwargs.get("clock_skew_in_seconds"), 10)

class ConfigTests(unittest.TestCase):
    def test_production_refuses_missing_or_placeholder_secret(self):
     
        for value in (None, "", "change-me", "dev-secret-change-me"):
            env = {"SECRET_KEY": value} if value is not None else {}
            with mock.patch.dict(os.environ, env, clear=True):
                if value is None:
                    os.environ.pop("SECRET_KEY", None)
                with self.assertRaises(RuntimeError):
                    config._load_secret_key("production")

    def test_production_accepts_real_secret_and_dev_allows_placeholder(self):
        
        with mock.patch.dict(os.environ, {"SECRET_KEY": "x" * 48}):
            self.assertEqual(config._load_secret_key("production"), "x" * 48)
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(config._load_secret_key("development"), "dev-secret-change-me")

# Test that users must verify their email before logging in.
class EmailVerificationTests(unittest.TestCase):
    def setUp(self):
        reset_rate_limits()
        self.client = create_app().test_client()

    def test_verify_email_rejects_bad_or_expired_token(self):
        from models.user_model import ValidationError
        with mock.patch("controllers.auth_controller.UserModel") as um:
            um.verify_email.side_effect = ValidationError("This verification link is invalid or has expired.")
            r = self.client.post("/api/auth/verify-email", json={"token": "bad"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("invalid or has expired", r.get_json()["error"])

    def test_verify_email_accepts_good_token(self):
        with mock.patch("controllers.auth_controller.UserModel") as um:
            r = self.client.post("/api/auth/verify-email", json={"token": "good"})
        self.assertEqual(r.status_code, 200)
        um.verify_email.assert_called_once_with("good")

    def test_resend_gives_same_answer_whether_or_not_the_account_exists(self):
        with mock.patch("controllers.auth_controller.UserModel") as um, \
             mock.patch("controllers.auth_controller.send_email_in_background") as send:
            um.create_verification_token.side_effect = ["tok", None]
            known = self.client.post("/api/auth/resend-verification", json={"email": "a@ku.th"})
            unknown = self.client.post("/api/auth/resend-verification", json={"email": "nobody@ku.th"})
        self.assertEqual(known.status_code, 200)
        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(known.get_json(), unknown.get_json())
        send.assert_called_once()  # Send mail only for an eligible account.

    def test_resend_rejects_missing_or_non_text_email(self):
        for body in ({}, {"email": ""}, {"email": 5}):
            self.assertEqual(
                self.client.post("/api/auth/resend-verification", json=body).status_code, 400, body)

    def test_login_blocked_until_email_is_verified(self):
        unverified = {**FAKE_USER, "email_verified": 0}
        with mock.patch("controllers.auth_controller.UserModel") as um:
            um.authenticate.return_value = unverified
            r = self.client.post("/api/auth/login", json={"email": "alice@ku.th", "password": "x"})
        self.assertEqual(r.status_code, 403)
        body = r.get_json()
        self.assertTrue(body["needs_verification"])
        self.assertEqual(body["email"], "alice@ku.th")
        self.assertNotIn("token", body)

    def test_login_works_once_verified(self):
        with mock.patch("controllers.auth_controller.UserModel") as um:
            um.authenticate.return_value = {**FAKE_USER, "email_verified": 1, "password_hash": "h"}
            r = self.client.post("/api/auth/login", json={"email": "alice@ku.th", "password": "x"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("token", r.get_json())

    def test_signup_returns_no_session_and_sends_the_link(self):
        with mock.patch("controllers.auth_controller.UserModel") as um, \
             mock.patch("controllers.auth_controller.send_email_in_background") as send:
            um.create_student_account.return_value = FAKE_USER
            um.create_verification_token.return_value = "tok"
            r = self.client.post("/api/auth/signup", json={"role": "undergrad_student"})
        self.assertEqual(r.status_code, 201)
        body = r.get_json()
        self.assertNotIn("token", body)
        self.assertEqual(body["email"], "alice@ku.th")
        self.assertIn("verify_token=tok", send.call_args[0][2])

if __name__ == "__main__":
    unittest.main()