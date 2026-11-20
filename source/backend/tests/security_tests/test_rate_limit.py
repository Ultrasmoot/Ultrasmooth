# rate limit and input validation tests
from security_tests.base import (
    FAKE_USER,
    ValidationTestsBase,
    create_app,
    mock,
    reset_rate_limits,
)  # noqa: F401
import unittest


class RateLimitTests(unittest.TestCase):
    def setUp(self):
        reset_rate_limits()
        self.client = create_app().test_client()

    def test_login_is_limited_with_429(self):
        with mock.patch("controllers.auth.controller.UserModel") as um:
            um.authenticate.return_value = None
            codes = [
                self.client.post("/api/auth/login", json={"email": "a@ku.th", "password": "x"}).status_code
                for _ in range(12)
            ]
        self.assertEqual(codes[:10], [401] * 10)
        self.assertEqual(codes[10:], [429, 429])

    def test_forgot_and_reset_are_limited(self):
        with mock.patch("controllers.auth.controller.UserModel") as um:
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


class ValidationTests_2(ValidationTestsBase):
    def test_signup_rejects_bad_input_without_500(self):
        with mock.patch("models.user.model.UserModel.find_by_email", return_value=None):
            for over in ({"password": "x" * 73}, {"password": 12345678}, {"full_name": ["a"]},
                         {"full_name": "n" * 151}, {"faculty": "f" * 151}, {"email": 5}):
                self.assertEqual(self._signup(**over).status_code, 400, over)

    def test_signup_undergrad_requires_valid_year(self):
        with mock.patch("models.user.model.UserModel.find_by_email", return_value=None):
            for bad in (None, "", 0, 7, "x", True):
                body = {} if bad is None else {"year": bad}
                self.assertEqual(self._signup(**body).status_code, 400, body)

    def test_signup_stores_year_for_undergrad_and_none_for_phd(self):
        from models.user.model import UserModel
        for role, given, expected in (("undergrad_student", 2, 2), ("phd_student", 2, None)):
            conn = mock.MagicMock()
            conn.cursor.return_value.lastrowid = 1
            with mock.patch("models.user.model.get_connection", return_value=conn), \
                 mock.patch.object(UserModel, "find_by_email", return_value=None), \
                 mock.patch.object(UserModel, "find_by_id", return_value=FAKE_USER):
                r = self._signup(role=role, year=given)
            self.assertEqual(r.status_code, 201, r.get_json())
            self.assertEqual(conn.cursor.return_value.execute.call_args_list[0][0][1][-1], expected)

    def test_signup_is_rate_limited(self):
        codes = [self._signup(role="admin").status_code for _ in range(11)]
        self.assertEqual(codes[:10], [400] * 10)
        self.assertEqual(codes[10], 429)