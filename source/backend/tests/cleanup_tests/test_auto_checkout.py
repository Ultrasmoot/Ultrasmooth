# automatic checkout tests
from cleanup_tests.base import (
    AutoCheckoutTestsBase,
    H,
    M,
    now,
    titles,
)  # noqa: F401


class AutoCheckoutTests_3(AutoCheckoutTestsBase):
    # checkout after 
    def test_closed_after_the_20_minute_grace_and_resource_freed(self):
        bid = self.booking(25)
        self.assertEqual(self.hk.auto_checkout_overdue(grace_minutes=20), 1)
        self.assertIsNotNone(self.row(bid)["checked_out_at"])
        self.assertEqual(self.status(), "Available")
        self.assertIn("You were checked out automatically", titles(self, self.student))
        self.assertIsNotNone(self.db.one("SELECT id FROM activity_log WHERE action = 'checkout.auto'"))

    def test_inside_the_grace_period_nothing_happens(self):
        bid = self.booking(10)
        self.assertEqual(self.hk.auto_checkout_overdue(grace_minutes=20), 0)
        self.assertIsNone(self.row(bid)["checked_out_at"])
        self.assertEqual(self.status(), "In Use")

    def test_not_checked_in_or_already_checked_out_are_left_alone(self):
        end = now() - 2 * H
        self.db.add_booking(self.res, self.student, end - H, end)  # never checked in
        self.db.add_booking(self.res, self.other, end - H, end, checked_in_at=end - H,
                            checked_out_at=end - 10 * M)  # already checked out
        self.assertEqual(self.hk.auto_checkout_overdue(grace_minutes=20), 0)

    def test_a_resource_in_maintenance_stays_blocked(self):
        self.db.execute("UPDATE resources SET status = 'Maintenance' WHERE id = %s", (self.res,))
        bid = self.booking(60)
        self.assertEqual(self.hk.auto_checkout_overdue(grace_minutes=20), 1)
        self.assertIsNotNone(self.row(bid)["checked_out_at"])
        self.assertEqual(self.status(), "Maintenance")

    def test_running_twice_does_not_repeat(self):
        self.booking(60)
        self.assertEqual(self.hk.auto_checkout_overdue(grace_minutes=20), 1)
        self.assertEqual(self.hk.auto_checkout_overdue(grace_minutes=20), 0)

    def test_the_resource_stays_in_use_if_another_session_is_running(self):
        self.booking(60)
        self.db.add_booking(self.res, self.other, now() - 30 * M, now() + H, checked_in_at=now() - 20 * M)
        self.hk.auto_checkout_overdue(grace_minutes=20)
        self.assertEqual(self.status(), "In Use")