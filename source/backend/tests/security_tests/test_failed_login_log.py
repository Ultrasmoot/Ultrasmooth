# failed login activity log tests
from security_tests.base_headers import (
    DbTestCase,
)  # noqa: F401


class FailedLoginLogTests(DbTestCase):
    def failed_rows(self):
        return self.call("get", "/api/activity?action=auth.login_failed&per_page=100", self.admin).get_json()["items"]

    def test_markup_and_line_breaks_are_not_stored(self):
        self.client.post("/api/auth/login", json={"email": "<img src=x onerror=alert(1)>\nfake@ku.th", "password": "x"})
        text = self.failed_rows()[0]["summary"] + self.failed_rows()[0]["actor_name"]
        for bad in ("<", ">", "\n", "=", " onerror"):
            self.assertNotIn(bad, text)

    def test_normal_address_is_still_logged_readably(self):
        self.client.post("/api/auth/login", json={"email": "Someone@ku.th", "password": "x"})
        self.assertEqual(self.failed_rows()[0]["summary"], "Failed login for Someone@ku.th")

    def test_long_text_is_cut(self):
        self.client.post("/api/auth/login", json={"email": "a" * 400 + "@ku.th", "password": "x"})
        self.assertLessEqual(len(self.failed_rows()[0]["actor_name"]), 100)

    def test_one_address_cannot_flood_the_log(self):
        # call directly bypass login rate limit
        from services.events import service as events
        for i in range(60):
            events.login_failed(f"u{i}@ku.th", ip="198.51.100.7")
        self.assertEqual(len(self.failed_rows()), events.LOGIN_LOG_PER_IP)

    def test_other_addresses_are_still_logged(self):
        for ip in ("198.51.100.1", "198.51.100.2"):
            self.client.post("/api/auth/login", json={"email": "x@ku.th", "password": "x"}, environ_overrides={"REMOTE_ADDR": ip})
        self.assertEqual(len(self.failed_rows()), 2)