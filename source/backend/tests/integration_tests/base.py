import datetime
import hashlib
import os
import re
import sys
import unittest
from unittest import mock

os.environ.setdefault("APP_ENV", "development")
import support 

DB_HOST = os.getenv("VASE_TEST_DB_HOST")
DB_PORT = int(os.getenv("VASE_TEST_DB_PORT", "3306"))
DB_USER = os.getenv("VASE_TEST_DB_USER", "root")
DB_PASSWORD = os.getenv("VASE_TEST_DB_PASSWORD", "")
DB_NAME = os.getenv("VASE_TEST_DB_NAME", "vase_test")

VERIFY = "controllers.auth.controller.id_token.verify_oauth2_token"
SCHEMA = os.path.join(support.BACKEND, "database", "schema.sql")
MIN = datetime.timedelta(minutes=1)


from integration_tests.setup_db import _statements, RealMySQLTestsBaseStatementsSetupclass  # noqa: E402
from integration_tests.helpers_account import RealMySQLTestsBaseRequestResetReset  # noqa: E402


@unittest.skipUnless(DB_HOST, "set VASE_TEST_DB_HOST to run the real-MySQL integration tests")
class RealMySQLTestsBase(RealMySQLTestsBaseStatementsSetupclass, RealMySQLTestsBaseRequestResetReset, unittest.TestCase):
    pass


if __name__ == "__main__":
    unittest.main()
