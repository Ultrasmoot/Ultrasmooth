# user and access management
import os
import sys

import support  # noqa: F401,E402

from support.sqlite_db import DbTestCase  # noqa: E402

URL = "/api/admin/users"


class UserManagementTestsBase(DbTestCase):
    NEW_STUDENT = {"full_name": "New Student", "email": "new.student@ku.th", "role": "undergrad_student",
                   "year": 2, "student_id": "6610000099", "password": "Passw0rd!x"}

    def create(self, uid=None, **extra):
        return self.call("post", URL, uid or self.admin, {**self.NEW_STUDENT, **extra})

    def login(self, email, password):
        return self.client.post("/api/auth/login", json={"email": email, "password": password})

    def actions(self):
        rows = self.call("get", "/api/activity", self.admin).get_json()["items"]
        return [(r["action"], r["actor_name"]) for r in rows]

    def uid_of(self, email):
        from models.user.model import UserModel
        return UserModel.find_by_email(email)["id"]

if __name__ == "__main__":
    import unittest
    unittest.main()