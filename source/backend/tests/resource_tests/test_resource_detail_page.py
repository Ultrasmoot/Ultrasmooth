from resource_tests.base import (
    H,
    ResourceDetailPageTestsBase,
    at,
) 
import datetime


class ResourceDetailPageTests_2(ResourceDetailPageTestsBase):
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
        self.db.add_booking(self.room, self.student, now - 3 * H, now - H, checked_in_at=now - 3 * H) # booked until 1 h ago
        using = self.detail(self.professor).get_json()["in_use_by"]
        self.assertEqual((using["name"], using["overdue"]), ("Demo Student", True))
        self.db.execute("UPDATE bookings SET end_time = %s", (now + H,))
        self.assertFalse(self.detail(self.admin).get_json()["in_use_by"]["overdue"])

    def test_schedule_lists_only_upcoming_approved_bookings_in_order(self):
        self.db.add_booking(self.room, self.student, at(3, 9), at(3, 10))
        self.db.add_booking(self.room, self.student, at(1, 9), at(1, 10))
        self.db.add_booking(self.room, self.student, at(2, 9), at(2, 10), status="Pending")
        self.db.add_booking(self.room, self.student, at(2, 12), at(2, 13), status="Rejected")
        self.db.add_booking(self.room, self.student, at(-3, 9), at(-3, 10)) # already over
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
