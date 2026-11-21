from calendar_tests.base import (
    DbTestCase,
    H,
    day_at,
)  
import datetime


class AppointmentCalendarTests(DbTestCase):

    def setUp(self):
        super().setUp()
        self.month_start = (datetime.date.today().replace(day=1) + datetime.timedelta(days=32)).replace(day=1)
        self.month = self.month_start.strftime("%Y-%m")
        self.mine = self.db.execute(
            "INSERT INTO appointments (professor_id, student_id, topic, start_time, end_time, status, created_at) "
            "VALUES (%s, %s, 'Testing help', %s, %s, 'Accepted', CURRENT_TIMESTAMP)",
            (self.professor, self.student, day_at(self.month_start, 10, 14), day_at(self.month_start, 10, 15)))
        self.waiting = self.db.execute(
            "INSERT INTO appointments (professor_id, student_id, topic, start_time, end_time, status, created_at) "
            "VALUES (%s, %s, 'Database design', %s, %s, 'Pending', CURRENT_TIMESTAMP)",
            (self.professor, self.other, day_at(self.month_start, 12, 10), day_at(self.month_start, 12, 11)))
        self.db.execute(
            "INSERT INTO appointments (professor_id, student_id, topic, start_time, end_time, status, created_at) "
            "VALUES (%s, %s, 'Declined one', %s, %s, 'Declined', CURRENT_TIMESTAMP)",
            (self.professor, self.other, day_at(self.month_start, 13, 10), day_at(self.month_start, 13, 11)))
        self.second_prof = self.db.add_user("professor", "Prof Malee", "malee@ku.th")
        self.db.execute(
            "INSERT INTO appointments (professor_id, student_id, topic, start_time, end_time, status, created_at) "
            "VALUES (%s, %s, 'Not yours', %s, %s, 'Accepted', CURRENT_TIMESTAMP)",
            (self.second_prof, self.student, day_at(self.month_start, 11, 10), day_at(self.month_start, 11, 11)))

    def get(self, uid, month=None):
        return self.call("get", f"/api/calendar/appointments?month={month or self.month}", uid)

    def test_only_professors_can_open_it(self):
        self.assertEqual(self.get(self.admin).status_code, 403)
        self.assertEqual(self.get(self.student).status_code, 403)
        self.assertEqual(self.get(self.other).status_code, 403)
        self.assertEqual(self.call("get", "/api/calendar/appointments").status_code, 401)

    def test_professor_sees_own_accepted_and_pending_only(self):
        items = self.get(self.professor).get_json()["appointments"]
        self.assertEqual([(a["id"], a["status"], a["student_name"]) for a in items],
                         [(self.mine, "Accepted", "Demo Student"), (self.waiting, "Pending", "Other Student")])

    def test_another_professor_does_not_see_them(self):
        items = self.get(self.second_prof).get_json()["appointments"]
        self.assertEqual([a["topic"] for a in items], ["Not yours"])

    def test_pending_request_in_the_past_is_left_out(self):
        past = datetime.datetime.now() - 2 * H
        self.db.execute(
            "INSERT INTO appointments (professor_id, student_id, topic, start_time, end_time, status, created_at) "
            "VALUES (%s, %s, 'Too late', %s, %s, 'Pending', CURRENT_TIMESTAMP)",
            (self.professor, self.student, past, past + H / 2))
        month = past.strftime("%Y-%m")
        topics = [a["topic"] for a in self.get(self.professor, month=month).get_json()["appointments"]]
        self.assertNotIn("Too late", topics)

    def test_bad_month_is_400(self):
        self.assertEqual(self.get(self.professor, month="2026-99").status_code, 400)
