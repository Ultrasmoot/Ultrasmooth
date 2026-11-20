# user management access, listing, creation and editing tests
from user_tests.base import (
    URL,
    UserManagementTestsBase,
)  # noqa: F401


class UserManagementTests_1(UserManagementTestsBase):
    # access control
    def test_only_an_administrator_can_use_every_route(self):
        calls = [("get", URL, None), ("post", URL, self.NEW_STUDENT), ("put", f"{URL}/{self.student}", {"full_name": "X"}),
                 ("post", f"{URL}/{self.student}/deactivate", None), ("post", f"{URL}/{self.student}/reactivate", None)]
        for method, path, body in calls:
            self.assertEqual(self.call(method, path, None, body).status_code, 401, path)
            for uid in (self.student, self.professor):
                self.assertEqual(self.call(method, path, uid, body).status_code, 403, (path, uid))

    # user listing
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

    # user creation
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

    def test_create_validation(self):
        bad = [
            ({"full_name": ""}, "Full name"), ({"full_name": 5}, "Full name"),
            ({"email": "not-an-email"}, "email"), ({"email": ""}, "Email"),
            ({"role": "superuser"}, "role"), ({"role": None}, "role"),
            ({"password": "short"}, "Password"), ({"password": None}, "Password"),
            ({"year": None}, "Year"), ({"year": 9}, "Year"),
            ({"student_id": "123"}, "Student ID"),
            ({"email": "student@ku.th"}, "already exists"),
        ]
        for extra, word in bad:
            r = self.create(**extra)
            self.assertEqual(r.status_code, 400, (extra, r.get_json()))
            self.assertIn(word.lower(), r.get_json()["error"].lower(), extra)
        self.assertEqual(self.call("get", URL, self.admin).get_json()["total"], 4)

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

    # user editing
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