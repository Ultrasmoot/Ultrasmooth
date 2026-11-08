import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlite_db import DbTestCase

URL = "/api/admin/users"


class UserManagementTests(DbTestCase):
    NEW_STUDENT = {"full_name": "New Student", "email": "new.student@ku.th", "role": "undergrad_student",
                   "year": 2, "student_id": "6610000099", "password": "Passw0rd!x"}

    def create(self, uid=None, **extra):
        return self.call("post", URL, uid or self.admin, {**self.NEW_STUDENT, **extra})

    def login(self, email, password):
        return self.client.post("/api/auth/login", json={"email": email, "password": password})

    def actions(self):
        rows = self.call("get", "/api/activity", self.admin).get_json()["items"]
        return [(r["action"], r["actor_name"]) for r in rows]

    # who may use it
    def test_only_an_administrator_can_use_every_route(self):
        calls = [("get", URL, None), ("post", URL, self.NEW_STUDENT), ("put", f"{URL}/{self.student}", {"full_name": "X"}),
                 ("post", f"{URL}/{self.student}/deactivate", None), ("post", f"{URL}/{self.student}/reactivate", None)]
        for method, path, body in calls:
            self.assertEqual(self.call(method, path, None, body).status_code, 401, path)
            for uid in (self.student, self.professor):
                self.assertEqual(self.call(method, path, uid, body).status_code, 403, (path, uid))

    # list
    def test_list_shows_everyone_and_never_a_password_hash(self):
        r = self.call("get", URL, self.admin)
        self.assertEqual(r.status_code, 200)
        users = r.get_json()["users"]
        self.assertEqual(len(users), 4)
        for u in users:
            self.assertNotIn("password_hash", u)
            self.assertNotIn("google_sub", u)
            self.assertTrue({"id", "full_name", "email", "role", "role_label", "is_active"} <= set(u))

    def test_list_filters_by_search_role_and_status(self):
        self.call("post", f"{URL}/{self.other}/deactivate", self.admin)
        ids = lambda qs: {u["id"] for u in self.call("get", f"{URL}?{qs}", self.admin).get_json()["users"]}
        self.assertEqual(ids("q=somchai"), {self.professor})
        self.assertEqual(ids("role=admin"), {self.admin})
        self.assertEqual(ids("status=inactive"), {self.other})
        self.assertEqual(ids("status=active"), {self.admin, self.professor, self.student})
        self.assertEqual(self.call("get", f"{URL}?role=wizard", self.admin).status_code, 400)
        self.assertEqual(self.call("get", f"{URL}?status=maybe", self.admin).status_code, 400)

    # create
    def test_create_a_student_who_can_log_in_straight_away(self):
        r = self.create()
        self.assertEqual(r.status_code, 201, r.get_json())
        u = r.get_json()["user"]
        self.assertEqual((u["role"], u["year"], u["is_active"], u["email_verified"]), ("undergrad_student", 2, True, True))
        self.assertEqual(self.login("new.student@ku.th", "Passw0rd!x").status_code, 200)
        self.assertEqual(self.login("new.student@ku.th", "wrong-password").status_code, 401)

    def test_create_a_professor_adds_them_to_the_directory_with_expertise(self):
        r = self.create(full_name="Dr. New Prof", email="new.prof@ku.th", role="professor", student_id=None, year=None,
                        expertise=" Databases, security ,databases ", bio="Query tuning.")
        self.assertEqual(r.status_code, 201, r.get_json())
        self.assertEqual(r.get_json()["user"]["expertise"], "Databases,security")
        listing = self.call("get", "/api/appointments/professors", self.student).get_json()["professors"]
        mine = [p for p in listing if p["name"] == "Dr. New Prof"]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["expertise"], ["Databases", "security"])

    def test_create_an_administrator(self):
        r = self.create(full_name="Second Admin", email="admin2@ku.th", role="admin", student_id=None, year=None)
        self.assertEqual(r.status_code, 201, r.get_json())
        self.assertEqual(self.call("get", "/api/admin/access-check", self.uid_of("admin2@ku.th")).status_code, 200)

    def uid_of(self, email):
        from models.user_model import UserModel
        return UserModel.find_by_email(email)["id"]

    def test_create_validation(self):
        bad = [
            ({"full_name": ""}, "Full name"), ({"full_name": 5}, "Full name"),
            ({"email": "not-an-email"}, "email"), ({"email": ""}, "Email"),
            ({"role": "superuser"}, "role"), ({"role": None}, "role"),
            ({"password": "short"}, "Password"), ({"password": None}, "Password"),
            ({"year": None}, "Year"), ({"year": 9}, "Year"),
            ({"student_id": "123"}, "Student ID"),
            ({"email": "student@ku.th"}, "already exists"), # taken by the demo student
        ]
        for extra, word in bad:
            r = self.create(**extra)
            self.assertEqual(r.status_code, 400, (extra, r.get_json()))
            self.assertIn(word.lower(), r.get_json()["error"].lower(), extra)
        self.assertEqual(self.call("get", URL, self.admin).get_json()["total"], 4)   # nothing was half-created

    def test_create_rejects_a_duplicate_student_id_and_a_non_object_body(self):
        self.assertEqual(self.create().status_code, 201)
        r = self.create(email="someone.else@ku.th")
        self.assertEqual(r.status_code, 400)
        self.assertIn("student id", r.get_json()["error"].lower())
        self.assertEqual(self.call("post", URL, self.admin, None).status_code, 400)

    def test_email_is_stored_lower_case_and_trimmed(self):
        u = self.create(email="  Mixed.Case@KU.th ").get_json()["user"]
        self.assertEqual(u["email"], "mixed.case@ku.th")
        self.assertEqual(self.create(email="MIXED.CASE@ku.th", student_id="6610000098").status_code, 400)

    # ----- edit
    def test_edit_changes_the_fields_and_is_logged(self):
        r = self.call("put", f"{URL}/{self.student}", self.admin,
                      {"full_name": "Demo Student Renamed", "faculty": "Science", "year": 4})
        self.assertEqual(r.status_code, 200, r.get_json())
        u = r.get_json()["user"]
        self.assertEqual((u["full_name"], u["faculty"], u["year"], u["email"]), ("Demo Student Renamed", "Science", 4, "student@ku.th"))
        self.assertIn(("user.updated", "Demo Admin"), self.actions())

    def test_edit_with_no_real_change_logs_nothing(self):
        before = len(self.actions())
        r = self.call("put", f"{URL}/{self.student}", self.admin, {"full_name": "Demo Student"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(self.actions()), before)

    def test_edit_cannot_reuse_another_accounts_email(self):
        r = self.call("put", f"{URL}/{self.student}", self.admin, {"email": "other@ku.th"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("already uses", r.get_json()["error"])
        self.assertEqual(self.call("put", f"{URL}/{self.student}", self.admin, {"email": "student@ku.th"}).status_code, 200)

    def test_edit_an_unknown_user_is_404(self):
        self.assertEqual(self.call("put", f"{URL}/99999", self.admin, {"full_name": "X"}).status_code, 404)
        self.assertEqual(self.call("post", f"{URL}/99999/deactivate", self.admin).status_code, 404)
        self.assertEqual(self.call("post", f"{URL}/99999/reactivate", self.admin).status_code, 404)

    # roles
    def test_assign_and_change_roles_takes_effect_at_once(self):
        # student -> professor: sees the professor inbox, loses student-only routes
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
        self.assertEqual(self.call("put", f"{URL}/{self.admin}", self.admin, {"full_name": "Admin Renamed"}).status_code, 200)

    def test_one_admin_can_demote_another(self):
        a2 = self.create(full_name="Second Admin", email="admin2@ku.th", role="admin", student_id=None, year=None).get_json()["user"]["id"]
        r = self.call("put", f"{URL}/{a2}", self.admin, {"role": "professor"})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(self.call("get", "/api/admin/access-check", a2).status_code, 403)

    def test_the_last_active_administrator_cannot_be_demoted_or_deactivated(self):
        # The acting admin id is a stranger here, so only the "last admin" guard can stop it
        # (through the API the self-protection rules already stop the realistic cases).
        from models.user_admin_model import UserAdminModel
        from models.user_model import ValidationError
        with self.assertRaises(ValidationError):
            UserAdminModel.update(99999, self.admin, {"role": "professor"})
        with self.assertRaises(ValidationError):
            UserAdminModel.set_active(99999, self.admin, False)
        self.assertEqual(self.db.one("SELECT role, is_active FROM users WHERE id = %s", (self.admin,)),
                         {"role": "admin", "is_active": 1})

    # deactivate / reactivate
    def test_a_deactivated_account_cannot_log_in_and_its_token_stops_working(self):
        self.assertEqual(self.call("get", "/api/me/ping", self.student).status_code, 200)
        r = self.call("post", f"{URL}/{self.student}/deactivate", self.admin)
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertFalse(r.get_json()["user"]["is_active"])
        self.assertEqual(self.call("get", "/api/me/ping", self.student).status_code, 401)   # signed out at once
        u = self.create().get_json()["user"]
        self.call("post", f"{URL}/{u['id']}/deactivate", self.admin)
        self.assertEqual(self.login("new.student@ku.th", "Passw0rd!x").status_code, 401)    # right password, still refused
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

    # every change is in the activity log, with who did it
    def test_every_change_is_written_to_the_activity_log(self):
        u = self.create().get_json()["user"]
        self.call("put", f"{URL}/{u['id']}", self.admin, {"role": "phd_student"})
        self.call("post", f"{URL}/{u['id']}/deactivate", self.admin)
        self.call("post", f"{URL}/{u['id']}/reactivate", self.admin)
        got = {a for a, _ in self.actions()}
        self.assertTrue({"user.created", "user.role_changed", "user.deactivated", "user.reactivated"} <= got, got)


if __name__ == "__main__":
    import unittest
    unittest.main()
