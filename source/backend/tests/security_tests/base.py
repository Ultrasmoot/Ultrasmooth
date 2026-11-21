# security regression tests
import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("APP_ENV", "development")
import support  # noqa: F401,E402 

from app import create_app  # noqa: E402
from middleware.rate_limit import reset_rate_limits  # noqa: E402

VERIFY = "controllers.auth.controller.id_token.verify_oauth2_token"
GOOD = {"sub": "g-123", "email": "alice@ku.th", "email_verified": True, "name": "Alice"}
FAKE_USER = {"id": 7, "email": "alice@ku.th", "full_name": "Alice", "role": "undergrad_student"}


class ValidationTestsBase(unittest.TestCase):
    def setUp(self):
        reset_rate_limits()
        self.client = create_app().test_client()

    def _signup(self, **over):
        body = {"role": "undergrad_student", "student_id": "6512345678", "full_name": "A",
                "email": "a@ku.th", "password": "password123"}
        body.update(over)
        return self.client.post("/api/auth/signup", json=body)

if __name__ == "__main__":
    unittest.main()