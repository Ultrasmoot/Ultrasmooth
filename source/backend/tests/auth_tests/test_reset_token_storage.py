from auth_tests.base import (
    TokenTestsBase,
    UserModel,
    ValidationError,
    _conn,
    _hash_reset_token,
    _user,
    mock,
) 
import unittest


class TokenTests_3(TokenTestsBase):
    def test_full_reset_flow_revokes_the_old_token(self):
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
             mock.patch("controllers.auth.controller.send_email_in_background"):
            login = self.client.post("/api/auth/login", json={"email": "alice@ku.th", "password": "OldPassword1"})
            self.assertEqual(login.status_code, 200)
            old = login.get_json()["token"]
            auth = {"Authorization": f"Bearer {old}"}
            self.assertEqual(self.client.get("/api/me/ping", headers=auth).status_code, 200)

            self.assertEqual(self.client.post("/api/auth/forgot-password", json={"email": "alice@ku.th"}).status_code, 200)
            self.assertEqual(self.client.post("/api/auth/reset-password",
                                              json={"token": "wrong", "password": "NewPassword1"}).status_code, 400)
            self.assertEqual(self.client.get("/api/me/ping", headers=auth).status_code, 200)  # failed reset changes nothing
            self.assertEqual(self.client.post("/api/auth/reset-password",
                                              json={"token": "T0K", "password": "NewPassword1"}).status_code, 200)

            self.assertEqual(self.client.get("/api/me/ping", headers=auth).status_code, 401)   # old token revoked
            relogin = self.client.post("/api/auth/login", json={"email": "alice@ku.th", "password": "NewPassword1"})
            self.assertEqual(relogin.status_code, 200)
            new = {"Authorization": f"Bearer {relogin.get_json()['token']}"}
            self.assertEqual(self.client.get("/api/me/ping", headers=new).status_code, 200)


class ResetTokenStorageTests(unittest.TestCase):
    def test_only_a_hash_is_stored_and_older_links_are_retired(self):
        conn = _conn()
        with mock.patch.object(UserModel, "find_by_email", return_value=_user()), \
             mock.patch("models.user.model.get_connection", return_value=conn):
            token = UserModel.create_reset_token("alice@ku.th")
        calls = conn.cursor.return_value.execute.call_args_list
        retire, insert = calls[0][0], calls[1][0]
        self.assertIn("SET used = 1 WHERE user_id = %s AND used = 0", retire[0])
        self.assertIn("INSERT INTO password_resets", insert[0])
        stored = insert[1][1]
        self.assertNotEqual(stored, token)
        self.assertEqual(stored, _hash_reset_token(token))
        self.assertEqual(len(stored), 64)
        for call in calls:   # the plaintext token never reaches SQL
            self.assertNotIn(token, [str(x) for x in (call[0][1] if len(call[0]) > 1 else ())])

    def test_successful_reset_kills_every_other_outstanding_link(self):
        conn = _conn(rowcount=1)
        conn.cursor.return_value.fetchone.return_value = {"user_id": 3}
        with mock.patch("models.user.model.get_connection", return_value=conn), \
             mock.patch.object(UserModel, "_hash_password", return_value="new-hash"):
            UserModel.reset_password("tok", "password123")
        sqls = [c[0][0] for c in conn.cursor.return_value.execute.call_args_list]
        self.assertTrue(any("UPDATE users SET password_hash" in s for s in sqls))
        self.assertTrue(any("SET used = 1 WHERE user_id = %s AND used = 0" in s for s in sqls))
        conn.commit.assert_called_once()
