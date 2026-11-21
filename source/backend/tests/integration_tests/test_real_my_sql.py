from integration_tests.base import (
    MIN,
    RealMySQLTestsBase,
    VERIFY,
    mock,
) 
import datetime
import hashlib


class RealMySQLTests_1(RealMySQLTestsBase):
    # reset token flow (hashed in the DB)
    def test_reset_token_is_stored_as_a_hash_and_works_exactly_once(self):
        old_jwt, user_id = self.signup()
        token = self.request_reset()

        rows = self.sql("SELECT token, used FROM password_resets WHERE user_id = %s", (user_id,), fetch=True)
        self.assertEqual(len(rows), 1)
        self.assertNotEqual(rows[0]["token"], token) # plaintext never stored
        self.assertEqual(rows[0]["token"], hashlib.sha256(token.encode()).hexdigest())
        self.assertEqual(rows[0]["used"], 0)

        self.assertEqual(self.reset("not-a-real-token", "NewPassword1").status_code, 400)
        self.assertEqual(self.reset(token, "short").status_code, 400) # a typo does not burn the link
        self.assertEqual(self.sql("SELECT used FROM password_resets", fetch=True)[0]["used"], 0)

        self.assertEqual(self.reset(token, "NewPassword1").status_code, 200)
        self.assertEqual(self.sql("SELECT used FROM password_resets", fetch=True)[0]["used"], 1)
        self.assertEqual(self.login("NewPassword1").status_code, 200)
        self.assertEqual(self.login("OldPassword1").status_code, 401)
        self.assertEqual(self.reset(token, "AnotherPass1").status_code, 400) # single use
        self.assertEqual(self.login("NewPassword1").status_code, 200)

    def test_expired_reset_token_is_refused(self):
        self.signup()
        token = self.request_reset()
        self.sql("UPDATE password_resets SET expires_at = %s",
                 (datetime.datetime.utcnow() - 2 * MIN,))
        r = self.reset(token, "NewPassword1")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.login("OldPassword1").status_code, 200)

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

    # old JWTs are revoked
    def test_jwt_issued_before_a_reset_stops_working_and_a_new_one_works(self):
        old_jwt, _ = self.signup()
        self.assertEqual(self.ping(old_jwt), 200)
        self.assertEqual(self.reset(self.request_reset(), "NewPassword1").status_code, 200)
        self.assertEqual(self.ping(old_jwt), 401)
        new_jwt = self.login("NewPassword1").get_json()["token"]
        self.assertEqual(self.ping(new_jwt), 200)

    def test_google_link_clears_the_password_revokes_old_tokens_and_cannot_be_replaced(self):
        old_jwt, user_id = self.signup()
        r = self.google("g-FIRST")
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(r.get_json()["user"]["id"], user_id)
        row = self.sql("SELECT google_sub, password_hash FROM users WHERE id = %s", (user_id,), fetch=True)[0]
        self.assertEqual(row["google_sub"], "g-FIRST")
        self.assertIsNone(row["password_hash"])
        self.assertEqual(self.ping(old_jwt), 401) # password-era token revoked
        self.assertEqual(self.login("OldPassword1").status_code, 401)

        # A different Google identity with the same e-mail address must NOT take the account over.
        other = self.google("g-SOMEONE-ELSE")
        self.assertEqual(other.status_code, 403)
        self.assertNotIn("token", other.get_json())
        self.assertEqual(self.sql("SELECT google_sub FROM users WHERE id = %s", (user_id,), fetch=True)[0]["google_sub"],
                         "g-FIRST")
        self.assertEqual(self.google("g-FIRST").status_code, 200) # the real owner still gets in

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
