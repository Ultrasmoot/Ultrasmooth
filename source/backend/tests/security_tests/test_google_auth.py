# Google authentication and email verification tests
from security_tests.base import (
    FAKE_USER,
    GOOD,
    VERIFY,
    create_app,
    mock,
    reset_rate_limits,
)  # noqa: F401
import unittest


class GoogleAuthTests(unittest.TestCase):
    def setUp(self):
        reset_rate_limits()
        self.client = create_app().test_client()

    def test_complete_profile_rejects_unverified_body(self):
        # reject forged identity data 
        with mock.patch("controllers.auth.controller.UserModel") as um:
            r = self.client.post(
                "/api/auth/google/complete-profile",
                json={"google_sub": "evil", "email": "victim@ku.th", "role": "phd_student"},
            )
            self.assertEqual(r.status_code, 400)
            um.complete_google_signup.assert_not_called()

    def test_complete_profile_rejects_invalid_token(self):
        with mock.patch(VERIFY, side_effect=ValueError("bad")), mock.patch(
            "controllers.auth.controller.UserModel"
        ) as um:
            r = self.client.post(
                "/api/auth/google/complete-profile", json={"credential": "x", "role": "phd_student"}
            )
            self.assertEqual(r.status_code, 401)
            um.complete_google_signup.assert_not_called()

    def test_complete_profile_uses_token_identity_not_body(self):
        with mock.patch(VERIFY, return_value=GOOD), mock.patch(
            "controllers.auth.controller.UserModel"
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
            "controllers.auth.controller.UserModel"
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
        # reject invalid years 
        for body in ({}, {"year": None}, {"year": ""}, {"year": 0}, {"year": 7}, {"year": "abc"},
                     {"year": True}, {"year": 2.5}, {"year": [3]}):
            with mock.patch(VERIFY, return_value=GOOD), mock.patch(
                "models.user.model.get_connection"
            ) as gc:
                r = self.client.post(
                    "/api/auth/google/complete-profile",
                    json={"credential": "tok", "role": "undergrad_student", **body},
                )
                self.assertEqual(r.status_code, 400, body)
                gc.assert_not_called()

    def test_complete_profile_phd_does_not_need_year_and_stores_none(self):
        from models.user.model import UserModel
        conn = mock.MagicMock()
        conn.cursor.return_value.lastrowid = 9
        with mock.patch("models.user.model.get_connection", return_value=conn), \
             mock.patch.object(UserModel, "find_by_id", return_value=FAKE_USER):
            UserModel.complete_google_signup("g-1", "p@ku.th", "P", "phd_student", year=4)
        params = conn.cursor.return_value.execute.call_args[0][1]
        self.assertIsNone(params[-1])  # Ph.D. year

    def test_complete_profile_undergrad_year_is_stored_as_int(self):
        from models.user.model import UserModel
        conn = mock.MagicMock()
        conn.cursor.return_value.lastrowid = 9
        for given in (3, "3", " 3 "):
            with mock.patch("models.user.model.get_connection", return_value=conn), \
                 mock.patch.object(UserModel, "find_by_id", return_value=FAKE_USER):
                UserModel.complete_google_signup("g-1", "u@ku.th", "U", "undergrad_student", year=given)
            self.assertEqual(conn.cursor.return_value.execute.call_args[0][1][-1], 3)

    def test_complete_profile_rejects_wrong_domain_and_unverified_email(self):
        for payload in (
            {**GOOD, "email": "alice@gmail.com"},
            {**GOOD, "email_verified": False},
        ):
            with mock.patch(VERIFY, return_value=payload), mock.patch(
                "controllers.auth.controller.UserModel"
            ) as um:
                r = self.client.post(
                    "/api/auth/google/complete-profile",
                    json={"credential": "tok", "role": "phd_student"},
                )
                self.assertEqual(r.status_code, 403)
                um.complete_google_signup.assert_not_called()

    def test_google_login_does_not_leak_google_sub(self):
        with mock.patch(VERIFY, return_value=GOOD), mock.patch(
            "controllers.auth.controller.UserModel"
        ) as um:
            um.find_or_create_google_user.return_value = (None, True)
            r = self.client.post("/api/auth/google", json={"credential": "tok"})
            self.assertEqual(r.status_code, 200)
            self.assertNotIn("google_sub", r.get_json())


# email verification
class EmailVerificationTests(unittest.TestCase):
    def setUp(self):
        reset_rate_limits()
        self.client = create_app().test_client()

    def test_verify_email_rejects_bad_or_expired_token(self):
        from models.user.model import ValidationError
        with mock.patch("controllers.auth.controller.UserModel") as um:
            um.verify_email.side_effect = ValidationError("This verification link is invalid or has expired.")
            r = self.client.post("/api/auth/verify-email", json={"token": "bad"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("invalid or has expired", r.get_json()["error"])

    def test_verify_email_accepts_good_token(self):
        with mock.patch("controllers.auth.controller.UserModel") as um:
            r = self.client.post("/api/auth/verify-email", json={"token": "good"})
        self.assertEqual(r.status_code, 200)
        um.verify_email.assert_called_once_with("good")

    def test_resend_gives_same_answer_whether_or_not_the_account_exists(self):
        with mock.patch("controllers.auth.controller.UserModel") as um, \
             mock.patch("controllers.auth.controller.send_email_in_background") as send:
            um.create_verification_token.side_effect = ["tok", None]
            known = self.client.post("/api/auth/resend-verification", json={"email": "a@ku.th"})
            unknown = self.client.post("/api/auth/resend-verification", json={"email": "nobody@ku.th"})
        self.assertEqual(known.status_code, 200)
        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(known.get_json(), unknown.get_json())
        send.assert_called_once()  # only the eligible account gets an email

    def test_resend_rejects_missing_or_non_text_email(self):
        for body in ({}, {"email": ""}, {"email": 5}):
            self.assertEqual(
                self.client.post("/api/auth/resend-verification", json=body).status_code, 400, body)

    def test_login_blocked_until_email_is_verified(self):
        unverified = {**FAKE_USER, "email_verified": 0}
        with mock.patch("controllers.auth.controller.UserModel") as um:
            um.authenticate.return_value = unverified
            r = self.client.post("/api/auth/login", json={"email": "alice@ku.th", "password": "x"})
        self.assertEqual(r.status_code, 403)
        body = r.get_json()
        self.assertTrue(body["needs_verification"])
        self.assertEqual(body["email"], "alice@ku.th")
        self.assertNotIn("token", body)

    def test_login_works_once_verified(self):
        with mock.patch("controllers.auth.controller.UserModel") as um:
            um.authenticate.return_value = {**FAKE_USER, "email_verified": 1, "password_hash": "h"}
            r = self.client.post("/api/auth/login", json={"email": "alice@ku.th", "password": "x"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("token", r.get_json())

    def test_signup_returns_no_session_and_sends_the_link(self):
        with mock.patch("controllers.auth.controller.UserModel") as um, \
             mock.patch("controllers.auth.controller.send_email_in_background") as send:
            um.create_student_account.return_value = FAKE_USER
            um.create_verification_token.return_value = "tok"
            r = self.client.post("/api/auth/signup", json={"role": "undergrad_student"})
        self.assertEqual(r.status_code, 201)
        body = r.get_json()
        self.assertNotIn("token", body)
        self.assertEqual(body["email"], "alice@ku.th")
        self.assertIn("verify_token=tok", send.call_args[0][2])