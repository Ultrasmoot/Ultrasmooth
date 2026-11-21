from support.stubs.archive_base import ADMIN, ArchiveTestsBase, MIN, OTHER, PRINTER, PROFESSOR, STUDENT
from support.stubs.maintenance_base import _token
from models.booking.model import ValidationError as BookingError
from models.booking.model import BookingModel
from resource_tests.base import (AppointmentTestsBase,at,) 
import datetime


class ArchiveTests_2(ArchiveTestsBase):
    def test_one_live_booking_among_finished_ones_still_blocks(self):
        self.add(status="Approved", start=-300, end=-200)
        self.add(status="Rejected", start=60, end=120)
        self.add(status="Pending", start=300, end=360)
        self.assertRefused("active bookings")

    def test_refused_resource_can_be_archived_after_the_booking_is_rejected(self):
        bid = self.add(status="Pending", start=60, end=120)
        self.assertEqual(self.archive().status_code, 400)
        self.db.bookings[bid]["status"] = "Rejected"
        self.assertEqual(self.archive().status_code, 200)

    def test_unknown_resource(self):
        r = self.archive(rid=999)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "Resource not found.")

    # access + effect
    def test_only_admins_can_archive(self):
        for user in (STUDENT, OTHER, PROFESSOR):
            self.assertEqual(self.archive(user=user).status_code, 403, user)
        self.assertEqual(self.archive(user=None).status_code, 401)
        self.assertFalse(self.is_archived())

    def test_archived_resource_is_hidden_from_non_admins_and_cannot_be_booked(self):
        self.archive()
        hdr = lambda u: {"Authorization": f"Bearer {_token(u)}"}  # noqa: E731
        self.assertEqual(self.client.get(f"/api/resources/{PRINTER}", headers=hdr(STUDENT)).status_code, 404)
        self.assertEqual(self.client.get(f"/api/resources/{PRINTER}", headers=hdr(ADMIN)).status_code, 200)
        start = self.now + 600 * MIN
        with self.assertRaises(BookingError):
            BookingModel.create({"resource_id": PRINTER, "start_time": start.isoformat(),
                                 "end_time": (start + 60 * MIN).isoformat(), "purpose": "x"}, requester_id=STUDENT)


class AppointmentTests_5(AppointmentTestsBase):
    def test_a_time_that_has_passed_cannot_be_accepted_but_can_be_declined(self):
        appt = self.ask().get_json()["appointment"]["id"]
        self.db.execute("UPDATE appointments SET start_time = %s, end_time = %s WHERE id = %s",
                        (at(-1, 10), at(-1, 10) + datetime.timedelta(minutes=30), appt))
        self.assertIn("passed", self.decide(appt, "accept").get_json()["error"])
        self.assertEqual(self.decide(appt, "decline").status_code, 200)

    # cancelling
    def test_student_cancels_a_pending_request_and_the_professor_is_told(self):
        appt = self.ask().get_json()["appointment"]["id"]
        r = self.call("post", f"/api/appointments/{appt}/cancel", self.student)
        self.assertEqual((r.status_code, r.get_json()["appointment"]["status"]), (200, "Cancelled"))
        self.assertIn("Appointment request cancelled", self.titles(self.professor))
        self.assertEqual(self.decide(appt, "accept").status_code, 400)  

    def test_cancel_rules(self):
        appt = self.ask().get_json()["appointment"]["id"]
        self.assertEqual(self.call("post", f"/api/appointments/{appt}/cancel", self.other).status_code, 400)
        self.decide(appt, "decline")
        r = self.call("post", f"/api/appointments/{appt}/cancel", self.student)
        self.assertEqual(r.status_code, 400) 
        self.assertIn("pending or accepted", r.get_json()["error"])
        self.assertEqual(self.call("post", "/api/appointments/9999/cancel", self.student).status_code, 400)

    # lists
    def test_each_side_sees_only_their_own(self):
        self.ask(); self.ask(uid=self.other, prof=self.prof2, start_time=at(4).isoformat())
        self.assertEqual([a["student_name"] for a in self.mine()], ["Demo Student"])
        self.assertEqual([a["student_name"] for a in self.inbox()], ["Demo Student"])
        self.assertEqual([a["student_name"] for a in self.inbox(self.prof2)], ["Other Student"])
        self.assertEqual(self.mine(self.other)[0]["professor_name"], "Dr Anan")
