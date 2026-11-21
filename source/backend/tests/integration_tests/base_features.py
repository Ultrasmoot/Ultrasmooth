import datetime
import os
import sys
import unittest

os.environ.setdefault("APP_ENV", "development")
import support

DB_HOST = os.getenv("VASE_TEST_DB_HOST")
DB_PORT = int(os.getenv("VASE_TEST_DB_PORT", "3306"))
DB_USER = os.getenv("VASE_TEST_DB_USER", "root")
DB_PASSWORD = os.getenv("VASE_TEST_DB_PASSWORD", "")
DB_NAME = os.getenv("VASE_TEST_DB_NAME", "vase_test")
SCHEMA = os.path.join(support.BACKEND, "database", "schema.sql")
DAY = datetime.timedelta(days=1)


from integration_tests.setup_statements import _statements, FeaturesRealMySQLTestsBaseStatementsSetupclass2
from integration_tests.setup_statements import FeaturesRealMySQLTestsBaseWhen


@unittest.skipUnless(DB_HOST, "set VASE_TEST_DB_HOST to run the real-MySQL integration tests")
class FeaturesRealMySQLTestsBase(FeaturesRealMySQLTestsBaseStatementsSetupclass2, FeaturesRealMySQLTestsBaseWhen, unittest.TestCase):
    pass
if __name__ == "__main__":
    unittest.main()
