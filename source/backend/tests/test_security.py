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
                "g-123", "alice@ku.th", "Alice", "undergrad_student"
            )

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

if __name__ == "__main__":
    unittest.main()