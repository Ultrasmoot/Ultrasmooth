from auth_tests.base import (
    Config,
    TokenTestsBase,
    UserModel,
    mock,
    password_fingerprint,
) 
import datetime
import jwt
from auth_tests.base import GOOD, VERIFY, create_app, reset_rate_limits
import os
import unittest


class TokenTests_2(TokenTestsBase):
    def test_garbage_sub_is_401_never_500(self):
        for sub in ("abc", "", "7.5", " 7", "-1", "7; DROP", True, 7.5, [7], {"a": 7}, None):
            r = self.me(self.token(sub=sub)) if sub is not None else self.me(self.token(sub=None))
            self.assertEqual(r.status_code, 401, repr(sub))

    def test_token_without_or_with_wrong_pwf_is_rejected(self):
        self.assertEqual(self.me(self.token(pwf=None)).status_code, 401)
        self.assertEqual(self.me(self.token(pwf="0" * 32)).status_code, 401)
        self.assertEqual(self.me(self.token(pwf=12345)).status_code, 401)

    def test_expired_wrongly_signed_and_alg_none_tokens_are_rejected(self):
        expired = self.token(exp=datetime.datetime.utcnow() - datetime.timedelta(seconds=5))
        forged = jwt.encode({"sub": "7", "pwf": password_fingerprint("hash-1")}, "not-the-secret", algorithm="HS256")
        unsigned = jwt.encode({"sub": "7", "pwf": password_fingerprint("hash-1")}, None, algorithm="none")
        for tok in (expired, forged, unsigned):
            self.assertEqual(self.me(tok).status_code, 401)

    def test_fingerprint_is_keyed_stable_and_hides_the_hash(self):
        a = password_fingerprint("$2b$12$abcdefghijklmnopqrstuv")
        self.assertEqual(a, password_fingerprint("$2b$12$abcdefghijklmnopqrstuv"))
        self.assertNotEqual(a, password_fingerprint("$2b$12$zzzzzzzzzzzzzzzzzzzzzz"))
        self.assertNotIn("abcdefghij", a)
        with mock.patch.object(Config, "SECRET_KEY", "another-secret"):
            self.assertNotEqual(a, password_fingerprint("$2b$12$abcdefghijklmnopqrstuv"))

    def test_old_token_dies_after_a_password_reset_and_a_new_one_works(self):
        old = self.token()
        self.assertEqual(self.me(old).status_code, 200)
        self.user["password_hash"] = "hash-2-after-reset"
        self.assertEqual(self.me(old).status_code, 401) 
        with mock.patch.object(UserModel, "find_by_id", return_value=self.user):
            r = self.client.get("/api/me/ping", headers={"Authorization": f"Bearer {old}"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.me(self.token(pwf=password_fingerprint("hash-2-after-reset"))).status_code, 200)

    def test_old_token_dies_when_the_password_is_cleared_by_a_google_link(self):
        old = self.token()
        self.user["password_hash"] = None
        self.assertEqual(self.me(old).status_code, 401)

    def test_deactivated_user_token_is_rejected(self):
        tok = self.token()
        self.user["is_active"] = 0
        self.assertEqual(self.me(tok).status_code, 401)

# Google clock skew
class ClockSkewTests(unittest.TestCase):
    def setUp(self):
        reset_rate_limits()
        self.client = create_app().test_client()

    def test_configured_skew_is_passed_to_google_verification(self):
        for configured in (0, 10, 45):
            with mock.patch.object(Config, "GOOGLE_CLOCK_SKEW_SECONDS", configured), \
                 mock.patch(VERIFY, return_value=GOOD) as v, \
                 mock.patch.object(UserModel, "find_by_google_sub", return_value=None), \
                 mock.patch.object(UserModel, "find_by_email", return_value=None):
                self.client.post("/api/auth/google", json={"credential": "t"})
            self.assertEqual(v.call_args.kwargs["clock_skew_in_seconds"], configured)

    def test_default_is_10_seconds_and_the_environment_value_is_bounded(self):
        import config as config_module
        self.assertEqual(Config.GOOGLE_CLOCK_SKEW_SECONDS, 10)
        bounded = config_module._bounded_int_env
        for raw, expected in (("25", 25), ("999", 60), ("-5", 0), ("abc", 10), ("", 10)):
            with mock.patch.dict(os.environ, {"GOOGLE_CLOCK_SKEW_SECONDS": raw}):
                self.assertEqual(bounded("GOOGLE_CLOCK_SKEW_SECONDS", 10, 0, 60), expected, raw)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_CLOCK_SKEW_SECONDS", None)
            self.assertEqual(bounded("GOOGLE_CLOCK_SKEW_SECONDS", 10, 0, 60), 10)

    def test_clock_related_rejections_get_a_helpful_message_other_errors_stay_generic(self):
        for text in ("Token used too early, 1700000000 < 1700000030", "Token expired, 100 < 200"):
            with mock.patch(VERIFY, side_effect=ValueError(text)):
                r = self.client.post("/api/auth/google", json={"credential": "t"})
            self.assertEqual(r.status_code, 401, text)
            self.assertIn("clock", r.get_json()["error"])
        for text in ("Wrong number of segments", "Could not verify token signature.", "Token has wrong audience"):
            with mock.patch(VERIFY, side_effect=ValueError(text)):
                r = self.client.post("/api/auth/google/complete-profile", json={"credential": "t", "role": "phd_student"})
            self.assertEqual(r.status_code, 401, text)
            self.assertEqual(r.get_json()["error"], "Invalid Google token.")
