import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("APP_ENV", "development")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from middleware.rate_limit import reset_rate_limits  # noqa: E402

VERIFY = "controllers.auth_controller.id_token.verify_oauth2_token"
GOOD = {"sub": "g-123", "email": "alice@ku.th", "email_verified": True, "name": "Alice"}
FAKE_USER = {"id": 7, "email": "alice@ku.th", "full_name": "Alice", "role": "undergrad_student"}

