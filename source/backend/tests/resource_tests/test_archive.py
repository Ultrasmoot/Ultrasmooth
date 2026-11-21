from support.stubs.archive_base import ADMIN, ArchiveTestsBase, MIN, PRINTER, SCOPE
from support.stubs.archive_db import Cur
from support.stubs.maintenance_base import _token


class ArchiveTests_1(ArchiveTestsBase):
    # allowed
    def test_resource_with_no_bookings_can_be_archived(self):
        r = self.archive()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"status": "archived"})
        self.assertTrue(self.is_archived())

    def test_row_is_locked_while_the_checks_run(self):
        self.archive()
        self.assertTrue(any(s.startswith("select status from resources where id = %s for update")
                            for s in Cur.statements))

    def test_bookings_that_are_over_or_not_live_do_not_block_archiving(self):
        self.add(status="Approved", start=-300, end=-200) 
        self.add(status="Pending", start=-300, end=-200) 
        self.add(status="Rejected", start=60, end=120) 
        done = self.add(status="Approved", start=-30, end=240) 
        self.db.bookings[done].update(checked_in_at=self.now - 20 * MIN, checked_out_at=self.now - 5 * MIN)
        self.add(status="Approved", start=60, end=120, rid=SCOPE) 
        self.assertEqual(self.archive().status_code, 200)
        self.assertTrue(self.is_archived())

    def test_archiving_twice_is_harmless_and_unarchive_restores_it(self):
        self.assertEqual(self.archive().status_code, 200)
        self.assertEqual(self.archive().status_code, 200)
        r = self.client.post(f"/api/resources/{PRINTER}/unarchive",
                             headers={"Authorization": f"Bearer {_token(ADMIN)}"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(self.is_archived())

    # refused
    def test_in_use_resource_cannot_be_archived(self):
        self.db.resources[PRINTER]["status"] = "In Use"
        self.assertRefused("currently In Use")

    def test_resource_with_someone_checked_in_cannot_be_archived(self):
        bid = self.add(status="Approved", start=-30, end=90)
        self.db.bookings[bid]["checked_in_at"] = self.now - 20 * MIN
        self.db.resources[PRINTER]["status"] = "In Use"
        self.assertRefused("currently In Use")

    def test_future_pending_booking_blocks_archiving(self):
        self.add(status="Pending", start=60, end=120)
        self.assertRefused("active bookings")

    def test_future_approved_booking_blocks_archiving(self):
        self.add(status="Approved", start=24 * 60, end=25 * 60)
        self.assertRefused("active bookings")

    def test_approved_booking_that_is_running_now_blocks_archiving(self):
        self.add(status="Approved", start=-30, end=30)  # started, not checked in, not over
        self.assertRefused("active bookings")
