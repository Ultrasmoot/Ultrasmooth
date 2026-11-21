# security tests 
from security_tests.base import (
    GOOD,
    VERIFY,
    ValidationTestsBase,
    create_app,
    mock,
    reset_rate_limits,
)  # noqa: F401
import unittest


class ValidationTests_3(ValidationTestsBase):
    def test_reset_rejects_long_password_before_touching_db(self):
        from models.user.model import UserModel, ValidationError
        with mock.patch("models.user.model.get_connection") as gc:
            with self.assertRaises(ValidationError):
                UserModel.reset_password("tok", "x" * 73)
            gc.assert_not_called()

    def test_reset_token_consumed_by_single_conditional_update(self):
        from models.user.model import UserModel, ValidationError
        conn = mock.MagicMock()
        cur = conn.cursor.return_value
        cur.rowcount = 0  # already used, expired or consumed by another request
        with mock.patch("models.user.model.get_connection", return_value=conn):
            with self.assertRaises(ValidationError):
                UserModel.reset_password("tok", "password123")
        conn.rollback.assert_called()
        conn.commit.assert_not_called()

        conn = mock.MagicMock()
        cur = conn.cursor.return_value
        cur.rowcount = 1
        cur.fetchone.return_value = {"user_id": 3}
        with mock.patch("models.user.model.get_connection", return_value=conn), \
             mock.patch.object(UserModel, "_hash_password", return_value="h"):
            UserModel.reset_password("tok", "password123")
        conn.commit.assert_called_once()


# reject invalid JSON types
class WrongTypeTests(unittest.TestCase):
    def setUp(self):
        reset_rate_limits()
        self.client = create_app().test_client()

    def test_login_and_forgot_password_reject_non_text_values(self):
        with mock.patch("models.user.model.get_connection") as gc:
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
        from models.user.model import UserModel
        good = UserModel._hash_password("password123")
        self.assertTrue(UserModel._check_password("password123", good))
        self.assertFalse(UserModel._check_password("x" * 100, good))          # over bcrypt
        self.assertFalse(UserModel._check_password(12345678, good))           # not text
        self.assertFalse(UserModel._check_password("password123", "garbage"))  # invalid stored hash
        self.assertIsNone(UserModel.authenticate(123, "x"))
        self.assertIsNone(UserModel.authenticate("a@ku.th", ["x"]))


class GoogleDeactivatedAndOutageTests(unittest.TestCase):
    def setUp(self):
        reset_rate_limits()
        self.client = create_app().test_client()

    def test_google_sign_in_does_not_modify_a_deactivated_account(self):
        from models.user.model import UserModel
        inactive = {"id": 9, "email": "off@ku.th", "is_active": 0, "role": "phd_student",
                    "password_hash": "hash", "google_sub": None}
        with mock.patch.object(UserModel, "find_by_google_sub", return_value=None), \
             mock.patch.object(UserModel, "find_by_email", return_value=inactive), \
             mock.patch("models.user.model.get_connection") as gc:
            user, is_new = UserModel.find_or_create_google_user("g-1", "off@ku.th", "Off")
        self.assertEqual((user, is_new), (inactive, False))
        gc.assert_not_called()  # no linking password removal

    def test_google_login_of_a_deactivated_account_is_403(self):
        inactive = {"id": 9, "email": "alice@ku.th", "is_active": 0, "role": "phd_student"}
        with mock.patch(VERIFY, return_value=GOOD), \
             mock.patch("controllers.auth.controller.UserModel") as um:
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