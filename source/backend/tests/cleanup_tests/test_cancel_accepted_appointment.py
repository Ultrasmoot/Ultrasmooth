# acepted appointment cancellation tests
from cleanup_tests.base import (
    DAY,
    DbTestCase,
    M,
    now,
    titles,
)  # noqa: F401


class CancelAcceptedAppointmentTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute("INSERT INTO professor_profiles (user_id, expertise, bio) VALUES (%s, 'Testing', 'x')",
                        (self.professor,))

    def appt(self, status="Accepted", start=None):
        start = start or now() + 2 * DAY
        return self.db.execute(
            "INSERT INTO appointments (student_id, professor_id, topic, start_time, end_time, status, created_at) "
            "VALUES (%s, %s, 'Thesis topic', %s, %s, %s, %s)",
            (self.student, self.professor, start, start + 30 * M, status, now()))

    def cancel(self, aid, uid=None):
        return self.call("post", f"/api/appointments/{aid}/cancel", uid or self.student)

    # accepted appointment cancellation
    def test_accepted_future_appointment_can_be_cancelled_and_the_professor_is_told(self):
        aid = self.appt()
        r = self.cancel(aid)
        self.assertEqual((r.status_code, r.get_json()["appointment"]["status"]), (200, "Cancelled"))
        self.assertIn("Appointment cancelled", titles(self, self.professor))
        log = self.db.one("SELECT summary FROM activity_log WHERE action = 'appointment.cancelled'")
        self.assertIn("was accepted", log["summary"])

    def test_the_slot_is_free_for_the_professor_again(self):
        aid = self.appt(start=now() + 2 * DAY)
        self.cancel(aid)
        start = now() + 2 * DAY
        r = self.call("post", "/api/appointments", self.other,
                      {"professor_id": self.professor, "topic": "Another topic", "start_time": start.isoformat()})
        self.assertEqual(r.status_code, 201, r.get_json())
        new_id = r.get_json()["appointment"]["id"]
        self.assertEqual(self.call("post", f"/api/appointments/{new_id}/decide", self.professor,
                                   {"decision": "accept"}).status_code, 200)

    def test_accepted_that_has_started_cannot_be_cancelled(self):
        aid = self.appt(start=now() - 5 * M)
        r = self.cancel(aid)
        self.assertEqual(r.status_code, 400)
        self.assertIn("already started", r.get_json()["error"])

    def test_declined_or_cancelled_and_other_students_are_refused(self):
        self.assertEqual(self.cancel(self.appt("Declined")).status_code, 400)
        done = self.appt()
        self.assertEqual(self.cancel(done, self.other).status_code, 400)
        self.assertEqual(self.cancel(done).status_code, 200)
        self.assertEqual(self.cancel(done).status_code, 400)

    def test_pending_request_is_cancelled_as_before(self):
        r = self.cancel(self.appt("Pending"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("Appointment request cancelled", titles(self, self.professor))