# cleanup tests record retention and Google unlink email change
from cleanup_tests.base import (
    DAY,
    DbTestCase,
    H,
    mock,
    now,
)  # noqa: F401


class RetentionTests(DbTestCase):
    # record retention
    def setUp(self):
        super().setUp()
        from services.housekeeping import service as housekeeping
        self.hk = housekeeping

    def note(self, days_ago):
        self.db.execute("INSERT INTO notifications (user_id, kind, title, body, link_view, created_at) "
                        "VALUES (%s, 'x', 't', '', 'home', %s)", (self.student, now() - days_ago * DAY))

    def log(self, days_ago):
        self.db.execute("INSERT INTO activity_log (actor_name, action, summary, created_at) "
                        "VALUES ('System', 'booking.submitted', 's', %s)", (now() - days_ago * DAY,))

    def count(self, table):
        return self.db.one(f"SELECT COUNT(*) AS n FROM {table}")["n"]

    def test_old_rows_go_recent_rows_stay(self):
        for d in (1, 44, 46, 90):
            self.note(d)
            self.log(d)
        self.assertEqual(self.hk.purge_old_records(notification_days=45, activity_days=45), (2, 2))
        self.assertEqual((self.count("notifications"), self.count("activity_log")), (2, 2))

    def test_zero_days_keeps_everything(self):
        self.note(500)
        self.log(500)
        self.assertEqual(self.hk.purge_old_records(notification_days=0, activity_days=0), (0, 0))
        self.assertEqual((self.count("notifications"), self.count("activity_log")), (1, 1))

    def test_more_rows_than_one_batch(self):
        for _ in range(7):
            self.note(100)
        self.note(1)
        with mock.patch.object(self.hk, "DELETE_BATCH", 3):
            self.assertEqual(self.hk.purge_old_records(notification_days=45, activity_days=0), (7, 0))
        self.assertEqual(self.count("notifications"), 1)

    def test_run_once_does_both_jobs(self):
        self.note(100)
        res = self.db.add_resource("Printer", status="In Use")
        end = now() - H
        self.db.add_booking(res, self.student, end - H, end, checked_in_at=end - H)
        closed, deleted = self.hk.run_once(purge=True)
        self.assertEqual((closed, deleted[0]), (1, 1))


class GoogleUnlinkOnEmailChangeTests(DbTestCase):
    # google account linking
    def setUp(self):
        super().setUp()
        self.db.execute("UPDATE users SET google_sub = 'g-123' WHERE id = %s", (self.student,))

    def sub(self):
        return self.db.one("SELECT google_sub FROM users WHERE id = %s", (self.student,))["google_sub"]

    def test_changing_the_email_removes_the_google_link(self):
        r = self.call("put", f"/api/admin/users/{self.student}", self.admin, {"email": "new.address@ku.th"})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertIsNone(self.sub())
        self.assertFalse(r.get_json()["user"]["google_linked"])
        log = self.db.one("SELECT summary FROM activity_log WHERE action = 'user.updated'")
        self.assertIn("Google link removed", log["summary"])

    def test_other_edits_keep_the_link(self):
        r = self.call("put", f"/api/admin/users/{self.student}", self.admin, {"full_name": "Renamed Student"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.sub(), "g-123")

    def test_same_email_sent_again_keeps_the_link(self):
        self.call("put", f"/api/admin/users/{self.student}", self.admin, {"email": "student@ku.th", "faculty": "Eng"})
        self.assertEqual(self.sub(), "g-123")