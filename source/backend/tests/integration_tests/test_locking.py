import datetime
import os
import sys

import support

from support.sqlite_db import DbTestCase 

H = datetime.timedelta(hours=1)


class LockingTests(DbTestCase):
    def setUp(self):
        super().setUp()
        now = datetime.datetime.now().replace(microsecond=0)
        self.rid = self.db.add_resource("Printer")
        self.bid = self.db.add_booking(self.rid, self.student, now + H, now + 2 * H)

    def lock(self, resource_id, booking_id, **kw):
        from database.db import get_connection
        from services.locking.service import lock_resource_then_booking
        conn = get_connection()
        try:
            return lock_resource_then_booking(conn.cursor(dictionary=True), resource_id, booking_id, **kw)
        finally:
            conn.close()

    def test_returns_both_rows(self):
        resource, booking = self.lock(self.rid, self.bid)
        self.assertEqual(resource["status"], "Available")
        self.assertEqual(booking["id"], self.bid)

    def test_missing_rows_come_back_as_none(self):
        resource, booking = self.lock(9999, 9999)
        self.assertIsNone(resource)
        self.assertIsNone(booking)

    def test_columns_can_be_chosen(self):
        resource, _ = self.lock(self.rid, self.bid, resource_columns="status, is_archived")
        self.assertEqual(set(resource), {"status", "is_archived"})

    def test_cancel_still_works_through_the_helper(self):
        r = self.call("post", f"/api/bookings/{self.bid}/cancel", self.student)
        self.assertEqual(r.status_code, 200, r.get_json())
