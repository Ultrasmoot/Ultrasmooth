# Part 1 of the tests in test_booking_in_use.py
from support.stubs.in_use_base import ARCHIVED, CreateWhileInUseTestsBase, MIN, OTHER, PRINTER, SCOPE
from models.checkin.model import EARLY_CHECKIN_MINUTES


class CreateWhileInUseTests_1(CreateWhileInUseTestsBase):
    def test_slot_that_starts_before_the_current_session_ends_is_refused(self):
        self.occupy(ends_in_min=120)
        self.assertRefused("in use until", 60)
        self.assertRefused("in use until", 5)
        self.assertEqual([b["requester_id"] for b in self.db.bookings.values()], [OTHER])  # nothing inserted

    def test_slot_starting_exactly_when_the_session_ends_or_later_is_allowed(self):
        self.occupy(ends_in_min=120)
        booking = self.book(120)
        self.assertEqual(booking["status"], "Pending")
        self.assertEqual(self.book(24 * 60 + 5, uid=OTHER)["status"], "Pending")

    def test_user_who_overstayed_does_not_block_later_slots(self):
        # Their booking ended 30 minutes ago but they have not checked out yet.
        self.occupy(ends_in_min=-30)
        self.assertEqual(self.book(1)["status"], "Pending")
        self.assertEqual(self.book(300)["status"], "Pending")

    def test_status_set_by_hand_without_a_session_blocks_only_the_check_in_window(self):
        self.in_use()  # nobody is checked in
        self.assertRefused("currently marked In Use", 5)
        self.assertRefused("currently marked In Use", EARLY_CHECKIN_MINUTES - 1)
        self.assertEqual(self.book(EARLY_CHECKIN_MINUTES + 1)["status"], "Pending")
        self.assertEqual(self.book(2 * 24 * 60, uid=OTHER)["status"], "Pending")

    def test_session_on_another_resource_does_not_matter(self):
        self.occupy(ends_in_min=600, rid=SCOPE)
        self.assertEqual(self.book(10, rid=PRINTER)["status"], "Pending")  # printer is Available

    def test_a_session_that_has_been_checked_out_no_longer_counts(self):
        bid = self.occupy(ends_in_min=30)
        self.db.bookings[bid]["checked_out_at"] = self.base - 5 * MIN
        # Printer is still marked In Use here (e.g. set by hand), but nobody is checked in,
        # so the rule falls back to the check-in-window check instead of "in use until ...".
        self.assertRefused("currently marked In Use", 5)
        self.db.resources[PRINTER]["status"] = "Available"
        self.assertEqual(self.book(60)["status"], "Pending")

    def test_available_resource_is_not_affected_by_the_rule(self):
        self.assertEqual(self.book(1)["status"], "Pending")

    def test_maintenance_and_archived_are_still_refused(self):
        self.db.resources[PRINTER]["status"] = "Maintenance"
        self.assertRefused("Maintenance", 60)
        self.assertRefused("does not exist", 60, rid=ARCHIVED)
        self.assertRefused("does not exist", 60, rid=999)

    def test_overlap_with_another_approved_booking_is_still_refused_for_in_use_resources(self):
        self.occupy(ends_in_min=30)
        # Somebody else already holds an approved slot later today.
        self.db.add_booking(rid=PRINTER, uid=OTHER, status="Approved",
                            start=self.base + 180 * MIN, end=self.base + 300 * MIN)
        self.assertRefused("already booked", 200)
        self.assertEqual(self.book(300)["status"], "Pending")
