from resource_tests.base import (
    AppointmentTestsBase,
    at,
)
import datetime


class AppointmentTests_3(AppointmentTestsBase):
    # who can do what
    def test_roles(self):
        self.assertEqual(self.call("get", "/api/appointments/professors").status_code, 401)
        for uid in (self.admin, self.professor):
            self.assertEqual(self.call("get", "/api/appointments/professors", uid).status_code, 403)
            self.assertEqual(self.ask(uid).status_code, 403)
            self.assertEqual(self.call("get", "/api/appointments/mine", uid).status_code, 403)
        for uid in (self.student, self.other, self.admin):
            self.assertEqual(self.call("get", "/api/appointments/inbox", uid).status_code, 403)
        appt = self.ask().get_json()["appointment"]["id"]
        for uid in (self.student, self.admin):
            self.assertEqual(self.decide(appt, "accept", uid).status_code, 403)

    # the professor directory
    def test_directory_shows_active_professors_with_expertise_and_never_an_email(self):
        self.db.add_user("professor", "Dr Retired", "retired@ku.th", active=0)
        r = self.call("get", "/api/appointments/professors", self.student).get_json()["professors"]
        self.assertEqual([p["name"] for p in r], ["Dr Anan", "Prof Somchai"])
        somchai = r[1]
        self.assertEqual(somchai["expertise"], ["Software testing", "Requirements engineering"])
        self.assertEqual((somchai["bio"], somchai["photo_url"]), ("Test automation", None))
        self.assertNotIn("@", str(r))

    def test_a_professor_without_a_profile_is_still_listed(self):
        self.db.add_user("professor", "Dr New", "new@ku.th")
        names = [p["name"] for p in self.call("get", "/api/appointments/professors", self.student).get_json()["professors"]]
        self.assertIn("Dr New", names)

    # asking
    def test_a_student_writes_their_own_topic(self):
        r = self.ask(topic="  How do I   pick a   thesis topic?  ")
        self.assertEqual(r.status_code, 201, r.get_json())
        a = r.get_json()["appointment"]
        self.assertEqual((a["topic"], a["status"], a["professor_name"]), ("How do I pick a thesis topic?", "Pending", "Prof Somchai"))
        self.assertEqual(a["end_time"], (at(3, 10) + datetime.timedelta(minutes=30)).isoformat())
        self.assertEqual(self.titles(self.professor), ["New appointment request"])
        self.assertEqual(self.titles(self.student), [])
        self.assertEqual(self.db.one("SELECT action FROM activity_log")["action"], "appointment.requested")

    def test_details_are_optional(self):
        self.assertEqual(self.ask(details="").status_code, 201)
        self.assertIsNone(self.mine()[0]["details"])

    def test_invalid_requests_are_400(self):
        bad = [{"topic": ""}, {"topic": "  "}, {"topic": "ab"}, {"topic": "x" * 101}, {"topic": 5}, {"topic": None},
               {"details": "x" * 501}, {"details": 5}, {"start_time": ""}, {"start_time": "tomorrow"}, {"start_time": 12345},
               {"start_time": at(-1).isoformat()}, {"start_time": at(400).isoformat()},
               {"professor_id": 9999}, {"professor_id": self.admin}, {"professor_id": self.student}, {"professor_id": "x"},
               {"professor_id": True}, {"professor_id": None}]
        for extra in bad:
            self.assertEqual(self.ask(**extra).status_code, 400, extra)
        self.assertEqual(self.mine(), [])
        self.assertEqual(self.call("post", "/api/appointments", self.student, None).status_code, 400)

    def test_cannot_ask_a_deactivated_professor(self):
        self.db.execute("UPDATE users SET is_active = 0 WHERE id = %s", (self.prof2,))
        self.assertEqual(self.ask(prof=self.prof2).status_code, 400)

    def test_at_most_three_pending_requests(self):
        for day in (3, 4, 5):
            self.assertEqual(self.ask(start_time=at(day).isoformat()).status_code, 201)
        r = self.ask(start_time=at(6).isoformat())
        self.assertEqual(r.status_code, 400)
        self.assertIn("3 pending", r.get_json()["error"])
        self.call("post", f"/api/appointments/{self.mine()[0]['id']}/cancel", self.student)
        self.assertEqual(self.ask(start_time=at(6).isoformat()).status_code, 201)       # cancelling frees a place
        self.assertEqual(self.ask(uid=self.other, start_time=at(3).isoformat()).status_code, 201)   # per student
