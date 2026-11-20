# user role, account status and activity log tests
from user_tests.base import (
    URL,
    UserManagementTestsBase,
)  # noqa: F401


class UserManagementTests_2(UserManagementTestsBase):
    # unknown users
    def test_edit_an_unknown_user_is_404(self):
        self.assertEqual(self.call("put", f"{URL}/99999", self.admin, {"full_name": "X"}).status_code, 404)
        self.assertEqual(self.call("post", f"{URL}/99999/deactivate", self.admin).status_code, 404)
        self.assertEqual(self.call("post", f"{URL}/99999/reactivate", self.admin).status_code, 404)

    # role management
    def test_assign_and_change_roles_takes_effect_at_once(self):
        # student becomes professor 
        self.assertEqual(self.call("get", "/api/appointments/inbox", self.student).status_code, 403)
        r = self.call("put", f"{URL}/{self.student}", self.admin, {"role": "professor", "expertise": "Testing"})
        self.assertEqual(r.status_code, 200, r.get_json())
        u = r.get_json()["user"]
        self.assertEqual((u["role"], u["year"], u["expertise"]), ("professor", None, "Testing"))
        self.assertEqual(self.call("get", "/api/appointments/inbox", self.student).status_code, 200)
        self.assertEqual(self.call("get", "/api/appointments/mine", self.student).status_code, 403)
        self.assertIn(("user.role_changed", "Demo Admin"), self.actions())

    def test_role_change_to_undergraduate_needs_a_year_and_leaving_it_clears_the_year(self):
        r = self.call("put", f"{URL}/{self.other}", self.admin, {"role": "undergrad_student"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("year", r.get_json()["error"].lower())
        r = self.call("put", f"{URL}/{self.other}", self.admin, {"role": "undergrad_student", "year": 1})
        self.assertEqual(r.get_json()["user"]["year"], 1)
        r = self.call("put", f"{URL}/{self.other}", self.admin, {"role": "phd_student"})
        self.assertIsNone(r.get_json()["user"]["year"])

    def test_an_unknown_role_is_rejected(self):
        self.assertEqual(self.call("put", f"{URL}/{self.student}", self.admin, {"role": "root"}).status_code, 400)

    def test_an_administrator_cannot_change_their_own_role(self):
        self.create(full_name="Second Admin", email="admin2@ku.th", role="admin", student_id=None, year=None)
        r = self.call("put", f"{URL}/{self.admin}", self.admin, {"role": "professor"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("own role", r.get_json()["error"])
        self.assertEqual(self.db.one("SELECT role FROM users WHERE id = %s", (self.admin,))["role"], "admin")
        # own name can edited
        self.assertEqual(self.call("put", f"{URL}/{self.admin}", self.admin, {"full_name": "Admin Renamed"}).status_code, 200)

    def test_one_admin_can_demote_another(self):
        a2 = self.create(full_name="Second Admin", email="admin2@ku.th", role="admin", student_id=None, year=None).get_json()["user"]["id"]
        r = self.call("put", f"{URL}/{a2}", self.admin, {"role": "professor"})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(self.call("get", "/api/admin/access-check", a2).status_code, 403)

    def test_the_last_active_administrator_cannot_be_demoted_or_deactivated(self):
        from models.user_admin.model import UserAdminModel
        from models.user.model import ValidationError
        with self.assertRaises(ValidationError):
            UserAdminModel.update(99999, self.admin, {"role": "professor"})
        with self.assertRaises(ValidationError):
            UserAdminModel.set_active(99999, self.admin, False)
        self.assertEqual(self.db.one("SELECT role, is_active FROM users WHERE id = %s", (self.admin,)),
                         {"role": "admin", "is_active": 1})

    # account activation
    def test_a_deactivated_account_cannot_log_in_and_its_token_stops_working(self):
        self.assertEqual(self.call("get", "/api/me/ping", self.student).status_code, 200)
        r = self.call("post", f"{URL}/{self.student}/deactivate", self.admin)
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertFalse(r.get_json()["user"]["is_active"])
        self.assertEqual(self.call("get", "/api/me/ping", self.student).status_code, 401)  # Token revoked
        u = self.create().get_json()["user"]
        self.call("post", f"{URL}/{u['id']}/deactivate", self.admin)
        self.assertEqual(self.login("new.student@ku.th", "Passw0rd!x").status_code, 401)  # Login refused
        self.assertIn(("user.deactivated", "Demo Admin"), self.actions())

    def test_reactivating_restores_access(self):
        u = self.create().get_json()["user"]
        self.call("post", f"{URL}/{u['id']}/deactivate", self.admin)
        r = self.call("post", f"{URL}/{u['id']}/reactivate", self.admin)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["user"]["is_active"])
        self.assertEqual(self.login("new.student@ku.th", "Passw0rd!x").status_code, 200)
        self.assertIn(("user.reactivated", "Demo Admin"), self.actions())

    def test_deactivate_twice_and_reactivate_an_active_account_are_refused(self):
        self.assertEqual(self.call("post", f"{URL}/{self.student}/reactivate", self.admin).status_code, 400)
        self.assertEqual(self.call("post", f"{URL}/{self.student}/deactivate", self.admin).status_code, 200)
        r = self.call("post", f"{URL}/{self.student}/deactivate", self.admin)
        self.assertEqual(r.status_code, 400)
        self.assertIn("already", r.get_json()["error"])

    def test_an_administrator_cannot_deactivate_themselves(self):
        r = self.call("post", f"{URL}/{self.admin}/deactivate", self.admin)
        self.assertEqual(r.status_code, 400)
        self.assertIn("own account", r.get_json()["error"])
        self.assertEqual(self.call("get", "/api/me/ping", self.admin).status_code, 200)

    def test_a_deactivated_administrator_loses_admin_access(self):
        a2 = self.create(full_name="Second Admin", email="admin2@ku.th", role="admin", student_id=None, year=None).get_json()["user"]["id"]
        self.assertEqual(self.call("get", URL, a2).status_code, 200)
        self.assertEqual(self.call("post", f"{URL}/{a2}/deactivate", self.admin).status_code, 200)
        self.assertEqual(self.call("get", URL, a2).status_code, 401)

    def test_a_deactivated_professor_leaves_the_directory(self):
        self.call("post", f"{URL}/{self.professor}/deactivate", self.admin)
        names = [p["name"] for p in self.call("get", "/api/appointments/professors", self.student).get_json()["professors"]]
        self.assertNotIn("Prof Somchai", names)

    # activity log
    def test_every_change_is_written_to_the_activity_log(self):
        u = self.create().get_json()["user"]
        self.call("put", f"{URL}/{u['id']}", self.admin, {"role": "phd_student"})
        self.call("post", f"{URL}/{u['id']}/deactivate", self.admin)
        self.call("post", f"{URL}/{u['id']}/reactivate", self.admin)
        got = {a for a, _ in self.actions()}
        self.assertTrue({"user.created", "user.role_changed", "user.deactivated", "user.reactivated"} <= got, got)