import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlite_db import DbTestCase  # noqa: E402

H = datetime.timedelta(hours=1)
DAY = datetime.timedelta(days=1)


def at(days=1, hour=10, minute=0):
    return (datetime.datetime.now() + days * DAY).replace(hour=hour, minute=minute, second=0, microsecond=0)


class ResourceDetailFieldTests(DbTestCase):
    BASE = {"name": "Meeting Room A", "type": "Room", "category": "Rooms", "location": "Room 301", "owner": "Admin"}

    def create(self, **extra):
        return self.call("post", "/api/resources", self.admin, {**self.BASE, **extra})

    def test_details_are_saved_and_returned(self):
        r = self.create(building="Building 15", floor="3rd floor", capacity=30,
                        features=["Projector", "Whiteboard", "Power outlets", "Air conditioning"],
                        usage_notes="Seminars and group meetings.")
        self.assertEqual(r.status_code, 201, r.get_json())
        res = r.get_json()["resource"]
        self.assertEqual((res["building"], res["floor"], res["capacity"]), ("Building 15", "3rd floor", 30))
        self.assertEqual(res["features"], ["Projector", "Whiteboard", "Power outlets", "Air conditioning"])
        self.assertEqual(res["usage_notes"], "Seminars and group meetings.")
        listed = self.call("get", "/api/resources", self.student).get_json()["resources"][0]
        self.assertEqual(listed["capacity"], 30)

    def test_every_detail_is_optional(self):
        res = self.create().get_json()["resource"]
        self.assertEqual((res["building"], res["floor"], res["capacity"], res["features"], res["usage_notes"]),
                         (None, None, None, [], None))

    def test_features_given_as_text_are_cleaned(self):
        res = self.create(features=" Projector, Wi-Fi ,projector,,  Wi-Fi ").get_json()["resource"]
        self.assertEqual(res["features"], ["Projector", "Wi-Fi"])        # trimmed no blanks no duplicates

    def test_invalid_details_are_400_and_nothing_is_saved(self):
        bad = [{"capacity": 0}, {"capacity": -3}, {"capacity": "abc"}, {"capacity": True}, {"capacity": 12.5},
               {"capacity": 10 ** 6}, {"capacity": [5]}, {"building": 5}, {"building": "x" * 101}, {"floor": "x" * 51},
               {"usage_notes": "x" * 1001}, {"usage_notes": ["a"]}, {"features": 5}, {"features": [1, 2]},
               {"features": ["a,b"]}, {"features": ["x" * 41]}, {"features": [f"f{i}" for i in range(16)]},
               {"features": ["x" * 40] * 1 + [f"{i:0>38}" for i in range(14)]}]
        for extra in bad:
            r = self.create(**extra)
            self.assertEqual(r.status_code, 400, extra)
        self.assertEqual(self.db.one("SELECT COUNT(*) AS n FROM resources")["n"], 0)

    def test_update_touches_only_what_was_sent_and_can_clear(self):
        rid = self.create(building="Building 15", capacity=30, features=["Projector"]).get_json()["resource"]["id"]
        r = self.call("put", f"/api/resources/{rid}", self.admin, {"capacity": 40})
        res = r.get_json()["resource"]
        self.assertEqual((res["capacity"], res["building"], res["features"]), (40, "Building 15", ["Projector"]))
        res = self.call("put", f"/api/resources/{rid}", self.admin, {"capacity": None, "building": "  ", "features": []}).get_json()["resource"]
        self.assertEqual((res["capacity"], res["building"], res["features"]), (None, None, []))
        self.assertEqual(self.call("put", f"/api/resources/{rid}", self.admin, {"capacity": "x"}).status_code, 400)

    def test_only_admin_can_change_details(self):
        rid = self.create().get_json()["resource"]["id"]
        for uid in (self.student, self.professor):
            self.assertEqual(self.call("put", f"/api/resources/{rid}", uid, {"capacity": 5}).status_code, 403)
            self.assertEqual(self.call("post", "/api/resources", uid, {**self.BASE, "capacity": 5}).status_code, 403)


class ResourceDetailPageTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.room = self.db.add_resource("Room A", "Rooms")
        self.detail = lambda uid, rid=None: self.call("get", f"/api/resources/{rid or self.room}/detail", uid)

    def test_login_required_and_unknown_is_404(self):
        self.assertEqual(self.detail(None).status_code, 401)
        self.assertEqual(self.detail(self.student, 9999).status_code, 404)

    def test_students_see_free_and_taken_slots_but_no_names_or_history(self):
        self.db.add_booking(self.room, self.other, at(1, 9), at(1, 11), purpose="Secret project")
        self.call("post", "/api/maintenance", self.admin, {"resource_id": self.room, "description": "Projector broken",
                  "date": datetime.date.today().isoformat()})
        body = self.detail(self.student).get_json()
        self.assertEqual(len(body["schedule"]), 1)
        self.assertEqual(set(body["schedule"][0]), {"start_time", "end_time"})
        for key in ("in_use_by", "maintenance", "activity"):
            self.assertNotIn(key, body)
        self.assertNotIn("Other Student", str(body))
        self.assertNotIn("Secret project", str(body))

    def test_staff_see_who_booked_the_repair_history_and_recent_activity(self):
        self.db.add_booking(self.room, self.other, at(1, 9), at(1, 11), purpose="Group meeting")
        self.call("post", "/api/maintenance", self.admin, {"resource_id": self.room, "description": "Projector broken",
                  "date": datetime.date.today().isoformat()})
        for uid in (self.admin, self.professor):
            body = self.detail(uid).get_json()
            self.assertEqual((body["schedule"][0]["requester_name"], body["schedule"][0]["purpose"]), ("Other Student", "Group meeting"))
            self.assertEqual(body["maintenance"][0]["description"], "Projector broken")
            self.assertEqual(body["activity"][0]["action_label"], "Issue reported")
            self.assertIsNone(body["in_use_by"])

    def test_staff_see_who_is_using_it_now_and_whether_they_are_overdue(self):
        now = datetime.datetime.now()
        self.db.add_booking(self.room, self.student, now - 3 * H, now - H, checked_in_at=now - 3 * H)   # booked until 1 h ago
        using = self.detail(self.professor).get_json()["in_use_by"]
        self.assertEqual((using["name"], using["overdue"]), ("Demo Student", True))
        self.db.execute("UPDATE bookings SET end_time = %s", (now + H,))
        self.assertFalse(self.detail(self.admin).get_json()["in_use_by"]["overdue"])

    def test_schedule_lists_only_upcoming_approved_bookings_in_order(self):
        self.db.add_booking(self.room, self.student, at(3, 9), at(3, 10))
        self.db.add_booking(self.room, self.student, at(1, 9), at(1, 10))
        self.db.add_booking(self.room, self.student, at(2, 9), at(2, 10), status="Pending")
        self.db.add_booking(self.room, self.student, at(2, 12), at(2, 13), status="Rejected")
        self.db.add_booking(self.room, self.student, at(-3, 9), at(-3, 10))                                # already over
        self.db.add_booking(self.room, self.other, at(4, 9), at(4, 10), checked_in_at=at(4, 9), checked_out_at=at(4, 10))
        starts = [s["start_time"] for s in self.detail(self.student).get_json()["schedule"]]
        self.assertEqual(starts, [at(1, 9).isoformat(), at(3, 9).isoformat()])

    def test_archived_resource_is_hidden_from_everyone_but_admin(self):
        self.db.execute("UPDATE resources SET is_archived = 1 WHERE id = %s", (self.room,))
        self.assertEqual(self.detail(self.student).status_code, 404)
        self.assertEqual(self.detail(self.professor).status_code, 404)
        self.assertEqual(self.detail(self.admin).status_code, 200)

    def test_details_come_with_the_resource(self):
        self.call("put", f"/api/resources/{self.room}", self.admin, {"capacity": 30, "features": ["Projector"], "floor": "3"})
        res = self.detail(self.student).get_json()["resource"]
        self.assertEqual((res["capacity"], res["features"], res["floor"]), (30, ["Projector"], "3"))


class AppointmentTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.db.execute("INSERT INTO professor_profiles (user_id, expertise, bio) VALUES (%s, %s, %s)",
                        (self.professor, "Software testing, Requirements engineering", "Test automation"))
        self.prof2 = self.db.add_user("professor", "Dr Anan", "anan@ku.th")
        self.db.execute("INSERT INTO professor_profiles (user_id, expertise, bio) VALUES (%s, %s, %s)",
                        (self.prof2, "Databases", "Schema design"))

    def ask(self, uid=None, prof=None, **extra):
        body = {"professor_id": prof or self.professor, "topic": "Testing strategy for our lab system",
                "details": "We have no tests yet", "start_time": at(3, 10).isoformat(), **extra}
        return self.call("post", "/api/appointments", uid or self.student, body)

    def decide(self, appt, decision, uid=None, **extra):
        return self.call("post", f"/api/appointments/{appt}/decide", uid or self.professor, {"decision": decision, **extra})

    def mine(self, uid=None):
        return self.call("get", "/api/appointments/mine", uid or self.student).get_json()["appointments"]

    def inbox(self, uid=None):
        return self.call("get", "/api/appointments/inbox", uid or self.professor).get_json()["appointments"]

    def titles(self, uid):
        return [n["title"] for n in self.call("get", "/api/notifications", uid).get_json()["notifications"]]

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

    # professor directory
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
        self.assertEqual(self.ask(start_time=at(6).isoformat()).status_code, 201)       # cancelling frees place
        self.assertEqual(self.ask(uid=self.other, start_time=at(3).isoformat()).status_code, 201)   # per student

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
        self.assertEqual(self.ask(start_time=at(3, 10, 15).isoformat()).status_code, 400)     # overlaps 15 min
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
        a3 = self.ask(start_time=at(3, 10, 30).isoformat()).get_json()["appointment"]["id"]   # same student
        self.assertEqual(self.decide(a1, "accept").status_code, 200)
        r = self.decide(a2, "accept")
        self.assertEqual(r.status_code, 400)
        self.assertIn("overlaps", r.get_json()["error"])
        self.assertEqual(self.mine(self.other)[0]["status"], "Pending")      # untouched
        self.assertEqual(self.decide(a3, "accept").status_code, 200)         # back to back
        self.assertEqual(self.decide(a2, "decline").status_code, 200)        # a clashing request can still be declined

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
        self.assertEqual(self.decide(appt, "accept").status_code, 400)                # no longer answerable

    def test_cancel_rules(self):
        appt = self.ask().get_json()["appointment"]["id"]
        self.assertEqual(self.call("post", f"/api/appointments/{appt}/cancel", self.other).status_code, 400)  
        self.decide(appt, "decline")
        r = self.call("post", f"/api/appointments/{appt}/cancel", self.student)
        self.assertEqual(r.status_code, 400)                                           # declined
        self.assertIn("pending or accepted", r.get_json()["error"])
        self.assertEqual(self.call("post", "/api/appointments/9999/cancel", self.student).status_code, 400)

    # lists
    def test_each_side_sees_only_their_own(self):
        self.ask(); self.ask(uid=self.other, prof=self.prof2, start_time=at(4).isoformat())
        self.assertEqual([a["student_name"] for a in self.mine()], ["Demo Student"])
        self.assertEqual([a["student_name"] for a in self.inbox()], ["Demo Student"])
        self.assertEqual([a["student_name"] for a in self.inbox(self.prof2)], ["Other Student"])
        self.assertEqual(self.mine(self.other)[0]["professor_name"], "Dr Anan")
