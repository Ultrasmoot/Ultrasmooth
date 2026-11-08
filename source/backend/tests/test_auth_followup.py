import datetime
import os
import sys
import time
import unittest
from unittest import mock

os.environ.setdefault("APP_ENV", "development")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import jwt  # noqa: E402

from app import create_app  # noqa: E402
from config import Config  # noqa: E402
from middleware.auth_middleware import password_fingerprint  # noqa: E402
from middleware.rate_limit import reset_rate_limits  # noqa: E402
from models.user_model import UserModel, ValidationError, _hash_reset_token  # noqa: E402
from services import mailer  # noqa: E402

VERIFY = "controllers.auth_controller.id_token.verify_oauth2_token"
GOOD = {"sub": "g-NEW", "email": "alice@ku.th", "email_verified": True, "name": "Alice"}


def _user(**over):
    base = {"id": 7, "email": "alice@ku.th", "full_name": "Alice", "role": "undergrad_student",
            "is_active": 1, "password_hash": "hash-1", "google_sub": None, "year": 3}
    base.update(over)
    return base


def _conn(rowcount=1):
    conn = mock.MagicMock()
    conn.cursor.return_value.rowcount = rowcount
    return conn


# Test Google account linking.
class GoogleLinkingModelTests(unittest.TestCase):
    def find(self, by_sub=None, by_email=None, fresh=None, rowcount=1):
        conn = _conn(rowcount)
        with mock.patch.object(UserModel, "find_by_google_sub", return_value=by_sub), \
             mock.patch.object(UserModel, "find_by_email", return_value=by_email), \
             mock.patch.object(UserModel, "find_by_id", return_value=fresh), \
             mock.patch("models.user_model.get_connection", return_value=conn):
            try:
                result = UserModel.find_or_create_google_user("g-NEW", "alice@ku.th", "Alice")
            finally:
                self.conn = conn
        return result

    def test_known_google_identity_signs_in_without_touching_the_db(self):
        known = _user(google_sub="g-NEW")
        user, is_new = self.find(by_sub=known)
        self.assertEqual((user, is_new), (known, False))
        self.conn.cursor.assert_not_called()

    def test_unknown_email_is_a_new_sign_up(self):
        self.assertEqual(self.find(), (None, True))
        self.conn.cursor.assert_not_called()

    def test_first_google_sign_in_links_the_existing_account_and_clears_its_password(self):
        before, after = _user(), _user(google_sub="g-NEW", password_hash=None)
        user, is_new = self.find(by_email=before, fresh=after)
        self.assertEqual((user, is_new), (after, False))
        sql, params = self.conn.cursor.return_value.execute.call_args[0]
        self.assertIn("password_hash = NULL", sql)
        self.assertIn("google_sub IS NULL OR google_sub = %s", sql)  # Make sure another Google link is not overwritten.
        self.assertEqual(params, ("g-NEW", 7, "g-NEW"))
        self.conn.commit.assert_called_once()

    def test_account_already_linked_to_a_different_google_identity_is_never_relinked(self):
        owner = _user(google_sub="g-SOMEONE-ELSE")
        with self.assertRaises(ValidationError) as ctx:
            self.find(by_email=owner)
        self.assertIn("different Google account", str(ctx.exception))
        self.conn.cursor.assert_not_called()  # Make sure the existing link and password stay unchanged.
        self.conn.commit.assert_not_called()

    def test_losing_a_race_to_another_link_is_an_error_not_an_overwrite(self):
        # Another request linked the account first, so no rows are updated.
        raced = _user(google_sub="g-SOMEONE-ELSE", password_hash=None)
        with self.assertRaises(ValidationError):
            self.find(by_email=_user(), fresh=raced, rowcount=0)

    def test_same_identity_arriving_twice_at_once_is_fine(self):
        already = _user(google_sub="g-NEW", password_hash=None)
        user, is_new = self.find(by_email=_user(), fresh=already, rowcount=0)
        self.assertEqual((user, is_new), (already, False))

    def test_deactivated_while_linking_is_reported_as_deactivated(self):
        off = _user(is_active=0)
        user, is_new = self.find(by_email=_user(), fresh=off, rowcount=0)
        self.assertEqual((user, is_new), (off, False))

    def test_deactivated_account_is_left_completely_alone(self):
        off = _user(is_active=0, google_sub="g-SOMEONE-ELSE")
        user, is_new = self.find(by_email=off)
        self.assertEqual((user, is_new), (off, False))
        self.conn.cursor.assert_not_called()


class GoogleLinkingEndpointTests(unittest.TestCase):
    def setUp(self):
        reset_rate_limits()
        self.client = create_app().test_client()

    def post(self, path="/api/auth/google", **body):
        return self.client.post(path, json={"credential": "tok", **body})

    def test_login_with_a_different_google_account_is_403_and_issues_no_token(self):
        with mock.patch(VERIFY, return_value=GOOD), \
             mock.patch.object(UserModel, "find_by_google_sub", return_value=None), \
             mock.patch.object(UserModel, "find_by_email", return_value=_user(google_sub="g-SOMEONE-ELSE")), \
             mock.patch("models.user_model.get_connection") as gc:
            r = self.post()
        self.assertEqual(r.status_code, 403)
        self.assertIn("different Google account", r.get_json()["error"])
        self.assertNotIn("token", r.get_json())
        gc.assert_not_called()

    def test_login_links_a_password_account_and_returns_a_token_for_that_account(self):
        linked = _user(google_sub="g-NEW", password_hash=None)
        with mock.patch(VERIFY, return_value=GOOD), \
             mock.patch.object(UserModel, "find_by_google_sub", return_value=None), \
             mock.patch.object(UserModel, "find_by_email", return_value=_user()), \
             mock.patch.object(UserModel, "find_by_id", return_value=linked), \
             mock.patch("models.user_model.get_connection", return_value=_conn()):
            r = self.post()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["user"]["id"], 7)
        claims = jwt.decode(r.get_json()["token"], Config.SECRET_KEY, algorithms=["HS256"])
        self.assertEqual(claims["sub"], "7")
        self.assertEqual(claims["pwf"], password_fingerprint(None))  # Make sure the token uses the cleared password value.

    def test_identity_comes_from_the_token_not_from_the_request_body(self):
        # Use the verified Google token instead of the account details in the request.
        with mock.patch(VERIFY, return_value=GOOD), \
             mock.patch.object(UserModel, "find_by_google_sub", return_value=None), \
             mock.patch.object(UserModel, "find_by_email", return_value=None) as by_email:
            r = self.post(email="victim@ku.th", google_sub="evil")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["needs_role"])
        by_email.assert_called_once_with("alice@ku.th")

    def test_complete_profile_for_an_existing_email_is_400_and_links_nothing(self):
        import mysql.connector
        conn = _conn()
        conn.cursor.return_value.execute.side_effect = mysql.connector.IntegrityError("dup")
        with mock.patch(VERIFY, return_value=GOOD), mock.patch("models.user_model.get_connection", return_value=conn):
            r = self.post("/api/auth/google/complete-profile", role="phd_student")
        self.assertEqual(r.status_code, 400)
        self.assertIn("already exists", r.get_json()["error"])
        conn.rollback.assert_called()
        self.assertNotIn("token", r.get_json())

    def test_unverified_email_and_foreign_domain_never_reach_the_linking_code(self):
        for payload in ({**GOOD, "email_verified": False}, {**GOOD, "email": "alice@gmail.com"},
                        {**GOOD, "email_verified": "true"}):
            with mock.patch(VERIFY, return_value=payload), \
                 mock.patch.object(UserModel, "find_or_create_google_user") as link:
                self.assertEqual(self.post().status_code, 403, payload)
            link.assert_not_called()


# Test JWT handling and token revocation.
class TokenTests(unittest.TestCase):
    def setUp(self):
        reset_rate_limits()
        self.client = create_app().test_client()
        self.user = _user()

    def token(self, **claims):
        payload = {"sub": "7", "pwf": password_fingerprint(self.user["password_hash"]),
                   "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1), **claims}
        payload = {k: v for k, v in payload.items() if v is not None}
        return jwt.encode(payload, Config.SECRET_KEY, algorithm="HS256")

    def me(self, token):
        with mock.patch.object(UserModel, "find_by_id", side_effect=lambda uid: self.user if uid == 7 else None):
            return self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    def test_issued_tokens_carry_a_string_sub(self):
        from controllers.auth_controller import _issue_token
        claims = jwt.decode(_issue_token(self.user), Config.SECRET_KEY, algorithms=["HS256"])
        self.assertEqual(claims["sub"], "7")
        self.assertIsInstance(claims["sub"], str)

    def test_string_sub_is_accepted(self):
        self.assertEqual(self.me(self.token(sub="7")).status_code, 200)

    def test_legacy_numeric_sub_is_accepted_whatever_the_pyjwt_version(self):
        # Test an older token with a numeric sub value.
        self.assertEqual(self.me(self.token(sub=7)).status_code, 200)

    def test_decode_does_not_depend_on_pyjwt_validating_sub(self):
        from middleware import auth_middleware
        with mock.patch.object(auth_middleware.jwt, "decode", return_value={"sub": 7}) as dec, \
             create_app().test_request_context(headers={"Authorization": "Bearer x"}):
            auth_middleware._decode_token()
        self.assertEqual(dec.call_args.kwargs["options"], {"verify_sub": False})
        self.assertEqual(dec.call_args.kwargs["algorithms"], ["HS256"])

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
        self.user["password_hash"] = "hash-2-after-reset"  # Simulate a password change during reset.
        self.assertEqual(self.me(old).status_code, 401)  # Make sure the old token no longer works.
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

    def test_full_reset_flow_revokes_the_old_token(self):
        # Test login, password reset, and login with the new password.
        sent = {}
        state = {"hash": UserModel._hash_password("OldPassword1")}
        user = _user(password_hash=state["hash"])

        def fake_reset(token, new_password):
            if token != sent.get("token"):
                raise ValidationError("This reset link is invalid or has expired.")
            user["password_hash"] = UserModel._hash_password(new_password)

        with mock.patch.object(UserModel, "find_by_email", return_value=user), \
             mock.patch.object(UserModel, "find_by_id", return_value=user), \
             mock.patch.object(UserModel, "create_reset_token", side_effect=lambda e: sent.setdefault("token", "T0K")), \
             mock.patch.object(UserModel, "reset_password", side_effect=fake_reset), \
             mock.patch("controllers.auth_controller.send_email_in_background"):
            login = self.client.post("/api/auth/login", json={"email": "alice@ku.th", "password": "OldPassword1"})
            self.assertEqual(login.status_code, 200)
            old = login.get_json()["token"]
            auth = {"Authorization": f"Bearer {old}"}
            self.assertEqual(self.client.get("/api/me/ping", headers=auth).status_code, 200)

            self.assertEqual(self.client.post("/api/auth/forgot-password", json={"email": "alice@ku.th"}).status_code, 200)
            self.assertEqual(self.client.post("/api/auth/reset-password",
                                              json={"token": "wrong", "password": "NewPassword1"}).status_code, 400)
            self.assertEqual(self.client.get("/api/me/ping", headers=auth).status_code, 200)  # Make sure a failed reset does not change the password.
            self.assertEqual(self.client.post("/api/auth/reset-password",
                                              json={"token": "T0K", "password": "NewPassword1"}).status_code, 200)

            self.assertEqual(self.client.get("/api/me/ping", headers=auth).status_code, 401)  # Make sure the old token is no longer valid.
            relogin = self.client.post("/api/auth/login", json={"email": "alice@ku.th", "password": "NewPassword1"})
            self.assertEqual(relogin.status_code, 200)
            new = {"Authorization": f"Bearer {relogin.get_json()['token']}"}
            self.assertEqual(self.client.get("/api/me/ping", headers=new).status_code, 200)


class ResetTokenStorageTests(unittest.TestCase):
    def test_only_a_hash_is_stored_and_older_links_are_retired(self):
        conn = _conn()
        with mock.patch.object(UserModel, "find_by_email", return_value=_user()), \
             mock.patch("models.user_model.get_connection", return_value=conn):
            token = UserModel.create_reset_token("alice@ku.th")
        calls = conn.cursor.return_value.execute.call_args_list
        retire, insert = calls[0][0], calls[1][0]
        self.assertIn("SET used = 1 WHERE user_id = %s AND used = 0", retire[0])
        self.assertIn("INSERT INTO password_resets", insert[0])
        stored = insert[1][1]
        self.assertNotEqual(stored, token)
        self.assertEqual(stored, _hash_reset_token(token))
        self.assertEqual(len(stored), 64)
        for call in calls:  # Make sure the plain reset token is never stored in SQL.
            self.assertNotIn(token, [str(x) for x in (call[0][1] if len(call[0]) > 1 else ())])

    def test_successful_reset_kills_every_other_outstanding_link(self):
        conn = _conn(rowcount=1)
        conn.cursor.return_value.fetchone.return_value = {"user_id": 3}
        with mock.patch("models.user_model.get_connection", return_value=conn), \
             mock.patch.object(UserModel, "_hash_password", return_value="new-hash"):
            UserModel.reset_password("tok", "password123")
        sqls = [c[0][0] for c in conn.cursor.return_value.execute.call_args_list]
        self.assertTrue(any("UPDATE users SET password_hash" in s for s in sqls))
        self.assertTrue(any("SET used = 1 WHERE user_id = %s AND used = 0" in s for s in sqls))
        conn.commit.assert_called_once()


# Test password reset email handling.
class MailerTests(unittest.TestCase):
    def test_smtp_connection_gets_the_configured_timeout_and_verified_tls(self):
        with mock.patch.object(Config, "SMTP_HOST", "smtp.example.com"), \
             mock.patch.object(Config, "SMTP_USER", "u"), mock.patch.object(Config, "SMTP_PASSWORD", "p"), \
             mock.patch.object(Config, "SMTP_TIMEOUT_SECONDS", 7), \
             mock.patch("services.mailer.smtplib.SMTP") as smtp:
            mailer.send_email("a@ku.th", "Subject", "Body")
        args, kwargs = smtp.call_args
        self.assertEqual(args, ("smtp.example.com", Config.SMTP_PORT))
        self.assertEqual(kwargs["timeout"], 7)
        server = smtp.return_value.__enter__.return_value
        self.assertIn("context", server.starttls.call_args.kwargs)  # Make sure the server certificate is verified.
        server.login.assert_called_once_with("u", "p")
        server.sendmail.assert_called_once()

    def test_default_timeout_is_set_and_finite(self):
        self.assertGreaterEqual(Config.SMTP_TIMEOUT_SECONDS, 1)
        self.assertLessEqual(Config.SMTP_TIMEOUT_SECONDS, 60)

    def test_without_smtp_host_the_message_is_only_logged(self):
        with mock.patch.object(Config, "SMTP_HOST", ""), mock.patch("services.mailer.smtplib.SMTP") as smtp, \
             mock.patch("builtins.print") as pr:
            mailer.send_email("a@ku.th", "S", "B", dev_log_line="link here")
        smtp.assert_not_called()
        self.assertIn("link here", pr.call_args[0][0])

    def test_background_send_returns_immediately_even_if_the_mail_server_hangs(self):
        release = []

        def slow(*a, **k):
            while not release:
                time.sleep(0.01)

        with mock.patch.object(mailer, "send_email", side_effect=slow):
            started = time.monotonic()
            thread = mailer.send_email_in_background("a@ku.th", "S", "B")
            elapsed = time.monotonic() - started
            self.assertLess(elapsed, 0.5)
            self.assertTrue(thread.daemon)
            release.append(1)
            thread.join(2)
        self.assertFalse(thread.is_alive())

    def test_background_failure_is_logged_and_never_raised(self):
        with mock.patch.object(mailer, "send_email", side_effect=OSError("smtp down")), \
             self.assertLogs("services.mailer", level="ERROR"):
            mailer.send_email_in_background("a@ku.th", "S", "B").join(2)

    def test_forgot_password_answers_the_same_and_fast_whether_or_not_the_account_exists(self):
        reset_rate_limits()
        client = create_app().test_client()
        gate = []

        def hanging_send(*a, **k):
            while not gate:
                time.sleep(0.01)

        with mock.patch.object(mailer, "send_email", side_effect=hanging_send):
            for token in ("T0K", None):  # Test with an existing account and a missing account.
                with mock.patch.object(UserModel, "create_reset_token", return_value=token):
                    reset_rate_limits()
                    started = time.monotonic()
                    r = client.post("/api/auth/forgot-password", json={"email": "alice@ku.th"})
                    self.assertLess(time.monotonic() - started, 1.0)
                    self.assertEqual(r.status_code, 200)
                    self.assertIn("If an account exists", r.get_json()["message"])
            gate.append(1)
            time.sleep(0.1)


# Test Google clock-skew settings.
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
        # Make sure clock errors get a helpful message.
        # Other Google token errors should keep the generic message.
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


if __name__ == "__main__":
    unittest.main()