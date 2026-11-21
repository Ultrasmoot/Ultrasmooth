# Part 2 of the tests in test_booking_reason.py

from support.stubs.checkin_base import RejectReasonTestsBase
from support.stubs.maintenance_base import _token
from support.stubs.checkin_sql_write import OTHER_STUDENT as OTHER, PROFESSOR, SCOPE, STUDENT
import datetime


class RejectReasonTests_2(RejectReasonTestsBase):
    def test_back_to_back_and_other_resource_bookings_do_not_block_approval(self):
        bid = self.db.pending()
        b = self.db.bookings[bid]
        # ends exactly when this one starts -> no overlap
        self.db.add_booking(rid=b["resource_id"], uid=OTHER, status="Approved",
                            start=b["start_time"] - datetime.timedelta(hours=2), end=b["start_time"])
        # same time, different resource
        self.db.add_booking(rid=SCOPE, uid=OTHER, status="Approved", start=b["start_time"], end=b["end_time"])
        self.assertEqual(self.decide(bid, "approve").status_code, 200)

    def test_wrong_json_types_are_a_400_not_a_500(self):
        bid = self.db.pending()
        for decision in (["approve"], {"a": 1}, 5, None, True):
            self.assertEqual(self.decide(bid, decision).status_code, 400, decision)
        self.assertEqual(self.decide(bid, "reject", reason=["x"]).status_code, 400)
        self.assertEqual(self.decide(bid, "reject", reason=123).status_code, 400)
        self.assertEqual(self.db.bookings[bid]["status"], "Pending")

    def test_only_admins_can_decide(self):
        bid = self.db.pending()
        for user in (STUDENT, OTHER, PROFESSOR):
            self.assertEqual(self.decide(bid, "reject", user=user, reason="no").status_code, 403, user)
        self.assertEqual(self.decide(bid, "reject", user=None, reason="no").status_code, 401)
        self.assertEqual(self.db.bookings[bid]["status"], "Pending")

    def test_a_second_decision_cannot_overwrite_the_first_reason(self):
        bid = self.db.pending()
        self.decide(bid, "reject", reason="First reason")
        r = self.decide(bid, "reject", reason="Second reason")
        self.assertEqual(r.status_code, 400)
        self.assertIn("already rejected", r.get_json()["error"])
        self.assertEqual(self.reason_of(bid), "First reason")

    def test_the_requester_sees_the_reason_but_other_students_do_not_see_the_booking(self):
        bid = self.db.pending(uid=STUDENT)
        self.decide(bid, "reject", reason="Resource is being serviced")
        token = {"Authorization": f"Bearer {_token(STUDENT)}"}
        mine = self.client.get("/api/bookings/mine", headers=token).get_json()["bookings"]
        self.assertEqual([(b["status"], b["decision_reason"]) for b in mine], [("Rejected", "Resource is being serviced")])
        other = self.client.get("/api/bookings/mine", headers={"Authorization": f"Bearer {_token(OTHER)}"})
        self.assertEqual(other.get_json()["bookings"], [])
