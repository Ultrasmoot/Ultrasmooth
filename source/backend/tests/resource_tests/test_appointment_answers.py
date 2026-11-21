from resource_tests.base import (
    AppointmentTestsBase,
    at,
) 
import datetime


class AppointmentTests_4(AppointmentTestsBase):
    def test_a_request_nobody_answered_in_time_does_not_count_against_the_limit(self):
        for day in (3, 4, 5):
            self.ask(start_time=at(day).isoformat())
        self.db.execute("UPDATE appointments SET start_time = %s, end_time = %s WHERE id = 1",
                        (at(-1, 10), at(-1, 10) + datetime.timedelta(minutes=30)))
        self.assertEqual(self.ask(start_time=at(6).isoformat()).status_code, 201)
        expired = [a for a in self.mine() if a["expired"]]
        self.assertEqual(len(expired), 1)

    def test_same_student_same_professor_overlapping_time_is_refused(self):
        self.ask()
        self.assertEqual(self.ask(start_time=at(3, 10, 15).isoformat()).status_code, 400)     # overlaps by 15 min
        self.assertEqual(self.ask(start_time=at(3, 10, 30).isoformat()).status_code, 201)     # starts when the first ends
        self.assertEqual(self.ask(prof=self.prof2, start_time=at(3, 10).isoformat()).status_code, 201)   # another professor

    # answering
    def test_professor_accepts_and_the_student_is_told(self):
        appt = self.ask().get_json()["appointment"]["id"]
        r = self.decide(appt, "accept")
        self.assertEqual((r.status_code, r.get_json()["appointment"]["status"]), (200, "Accepted"))
        self.assertEqual(self.titles(self.student), ["Appointment accepted"])
        self.assertEqual(self.mine()[0]["status"], "Accepted")
        self.assertEqual(self.db.one("SELECT action, actor_name FROM activity_log WHERE action = 'appointment.accepted'")["actor_name"], "Prof Somchai")

    def test_professor_declines_with_or_without_a_reason(self):
        a1 = self.ask(start_time=at(3).isoformat()).get_json()["appointment"]["id"]
        a2 = self.ask(start_time=at(4).isoformat()).get_json()["appointment"]["id"]
        r1 = self.decide(a1, "decline", reason="  I am travelling that week  ").get_json()["appointment"]
        r2 = self.decide(a2, "decline").get_json()["appointment"]
        self.assertEqual((r1["status"], r1["decision_reason"]), ("Declined", "I am travelling that week"))
        self.assertEqual((r2["status"], r2["decision_reason"]), ("Declined", None))
        note = self.call("get", "/api/notifications", self.student).get_json()["notifications"]
        self.assertIn("I am travelling that week", [n["body"] for n in note][1])
        self.assertEqual(self.decide(self.ask(start_time=at(5).isoformat()).get_json()["appointment"]["id"],
                                     "decline", reason="x" * 256).status_code, 400)

    def test_a_reason_is_ignored_when_accepting(self):
        appt = self.ask().get_json()["appointment"]["id"]
        self.assertIsNone(self.decide(appt, "accept", reason="not kept").get_json()["appointment"]["decision_reason"])

    def test_two_accepted_appointments_cannot_overlap(self):
        a1 = self.ask().get_json()["appointment"]["id"]
        a2 = self.ask(uid=self.other, start_time=at(3, 10, 15).isoformat()).get_json()["appointment"]["id"]
        a3 = self.ask(start_time=at(3, 10, 30).isoformat()).get_json()["appointment"]["id"]   # same student, starts when a1 ends
        self.assertEqual(self.decide(a1, "accept").status_code, 200)
        r = self.decide(a2, "accept")
        self.assertEqual(r.status_code, 400)
        self.assertIn("overlaps", r.get_json()["error"])
        self.assertEqual(self.mine(self.other)[0]["status"], "Pending") # untouched
        self.assertEqual(self.decide(a3, "accept").status_code, 200) # back-to-back is fine
        self.assertEqual(self.decide(a2, "decline").status_code, 200) # a clashing request can still be declined

    def test_only_the_asked_professor_can_answer(self):
        appt = self.ask().get_json()["appointment"]["id"]
        r = self.decide(appt, "accept", uid=self.prof2)
        self.assertEqual((r.status_code, r.get_json()["error"]), (400, "Appointment not found."))
        self.assertEqual(self.inbox(self.prof2), [])
        self.assertEqual(len(self.inbox()), 1)

    def test_a_request_can_only_be_answered_once_and_bad_decisions_are_400(self):
        appt = self.ask().get_json()["appointment"]["id"]
        self.decide(appt, "decline", reason="First")
        for decision in ("accept", "decline"):
            self.assertIn("already declined", self.decide(appt, decision, reason="Second").get_json()["error"])
        self.assertEqual(self.mine()[0]["decision_reason"], "First")
        for bad in (None, "", "approve", 5):
            self.assertEqual(self.decide(appt, bad).status_code, 400, bad)
        self.assertEqual(self.decide(9999, "accept").status_code, 400)
