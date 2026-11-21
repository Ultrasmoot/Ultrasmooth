import datetime
import os
import sys
import time
import unittest
from unittest import mock

os.environ.setdefault("APP_ENV", "development")
import support  

import jwt 

from app import create_app 
from config import Config  
from middleware.auth_middleware import password_fingerprint 
from middleware.rate_limit import reset_rate_limits  
from models.user.model import UserModel, ValidationError, _hash_reset_token 
from services.mailer import service as mailer

VERIFY = "controllers.auth.controller.id_token.verify_oauth2_token"
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


# jwt
class TokenTestsBase(unittest.TestCase):
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

if __name__ == "__main__":
    unittest.main()
