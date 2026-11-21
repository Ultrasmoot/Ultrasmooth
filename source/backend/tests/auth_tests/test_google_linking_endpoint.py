from auth_tests.base import (
    Config,
    GOOD,
    TokenTestsBase,
    UserModel,
    VERIFY,
    ValidationError,
    _conn,
    _user,
    create_app,
    mock,
    password_fingerprint,
    reset_rate_limits,
)  # noqa: F401
import jwt
import unittest

# Google sign-in must not link / overwrite the wrong account
class GoogleLinkingModelTests(unittest.TestCase):
    def find(self, by_sub=None, by_email=None, fresh=None, rowcount=1):
        conn = _conn(rowcount)
        with mock.patch.object(UserModel, "find_by_google_sub", return_value=by_sub), \
             mock.patch.object(UserModel, "find_by_email", return_value=by_email), \
             mock.patch.object(UserModel, "find_by_id", return_value=fresh), \
             mock.patch("models.user.model.get_connection", return_value=conn):
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
        self.assertIn("google_sub IS NULL OR google_sub = %s", sql)  # atomic: never overwrites another link
        self.assertEqual(params, ("g-NEW", 7, "g-NEW"))
        self.conn.commit.assert_called_once()

    def test_account_already_linked_to_a_different_google_identity_is_never_relinked(self):
        owner = _user(google_sub="g-SOMEONE-ELSE")
        with self.assertRaises(ValidationError) as ctx:
            self.find(by_email=owner)
        self.assertIn("different Google account", str(ctx.exception))
        self.conn.cursor.assert_not_called()   # no UPDATE at all: sub and password untouched
        self.conn.commit.assert_not_called()

    def test_losing_a_race_to_another_link_is_an_error_not_an_overwrite(self):
        # The row looked unlinked when read, but another request linked it first (rowcount 0)
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
             mock.patch("models.user.model.get_connection") as gc:
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
             mock.patch("models.user.model.get_connection", return_value=_conn()):
            r = self.post()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["user"]["id"], 7)
        claims = jwt.decode(r.get_json()["token"], Config.SECRET_KEY, algorithms=["HS256"])
        self.assertEqual(claims["sub"], "7")
        self.assertEqual(claims["pwf"], password_fingerprint(None))   # bound to the cleared password

    def test_identity_comes_from_the_token_not_from_the_request_body(self):
        # Body fields claiming to be someone else are ignored on both Google endpoints.
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
        with mock.patch(VERIFY, return_value=GOOD), mock.patch("models.user.model.get_connection", return_value=conn):
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


class TokenTests_1(TokenTestsBase):
    def test_issued_tokens_carry_a_string_sub(self):
        from controllers.auth.controller import _issue_token
        claims = jwt.decode(_issue_token(self.user), Config.SECRET_KEY, algorithms=["HS256"])
        self.assertEqual(claims["sub"], "7")
        self.assertIsInstance(claims["sub"], str)

    def test_string_sub_is_accepted(self):
        self.assertEqual(self.me(self.token(sub="7")).status_code, 200)

    def test_legacy_numeric_sub_is_accepted_whatever_the_pyjwt_version(self):
        # Built with PyJWT's encoder bypassed for the sub check, as an older release would have issued it.
        self.assertEqual(self.me(self.token(sub=7)).status_code, 200)

    def test_decode_does_not_depend_on_pyjwt_validating_sub(self):
        from middleware import auth_middleware
        with mock.patch.object(auth_middleware.jwt, "decode", return_value={"sub": 7}) as dec, \
             create_app().test_request_context(headers={"Authorization": "Bearer x"}):
            auth_middleware._decode_token()
        self.assertEqual(dec.call_args.kwargs["options"], {"verify_sub": False})
        self.assertEqual(dec.call_args.kwargs["algorithms"], ["HS256"])
