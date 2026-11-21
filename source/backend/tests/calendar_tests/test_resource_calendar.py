from calendar_tests.base import (
    DbTestCase,
    day_at,
)  
import datetime


class ResourceCalendarTests(DbTestCase):

    def setUp(self):
        super().setUp()
        self.month_start = (datetime.date.today().replace(day=1) + datetime.timedelta(days=32)).replace(day=1)
        self.month = self.month_start.strftime("%Y-%m")
        self.rid = self.db.add_resource("Laser Cutter")
        self.approved = self.db.add_booking(self.rid, self.student, day_at(self.month_start, 5, 10),
                                            day_at(self.month_start, 5, 12), purpose="Thesis parts")
        self.pending = self.db.add_booking(self.rid, self.other, day_at(self.month_start, 6, 9),
                                           day_at(self.month_start, 6, 10), status="Pending")
        self.db.add_booking(self.rid, self.other, day_at(self.month_start, 7, 9),
                            day_at(self.month_start, 7, 10), status="Rejected")
        self.db.add_booking(self.rid, self.other, day_at(self.month_start, 8, 9),
                            day_at(self.month_start, 8, 10), status="Cancelled")

    def get(self, uid, rid=None, month=None):
        return self.call("get", f"/api/calendar/resource/{rid or self.rid}?month={month or self.month}", uid)

    def test_needs_sign_in(self):
        self.assertEqual(self.call("get", f"/api/calendar/resource/{self.rid}").status_code, 401)

    def test_approved_and_pending_show_rejected_and_cancelled_do_not(self):
        body = self.get(self.student).get_json()
        self.assertEqual([(b["id"], b["status"]) for b in body["bookings"]],
                         [(self.approved, "Approved"), (self.pending, "Pending")])
        self.assertEqual(body["month"], self.month)

    def test_students_see_times_only(self):
        for uid in (self.student, self.other):
            for b in self.get(uid).get_json()["bookings"]:
                self.assertNotIn("requester_name", b)
                self.assertNotIn("purpose", b)

    def test_admin_and_professor_see_who_booked(self):
        for uid in (self.admin, self.professor):
            first = self.get(uid).get_json()["bookings"][0]
            self.assertEqual((first["requester_name"], first["purpose"]), ("Demo Student", "Thesis parts"))

    def test_other_months_are_empty(self):
        self.assertEqual(self.get(self.student, month="2020-01").get_json()["bookings"], [])

    def test_booking_crossing_midnight_shows_in_both_months(self):
        last = (self.month_start + datetime.timedelta(days=40)).replace(day=1) - datetime.timedelta(days=1)
        nxt = last + datetime.timedelta(days=1)
        self.db.add_booking(self.rid, self.student, datetime.datetime.combine(last, datetime.time(23)),
                            datetime.datetime.combine(nxt, datetime.time(1)))
        for month in (last.strftime("%Y-%m"), nxt.strftime("%Y-%m")):
            ids = [b["start_time"] for b in self.get(self.student, month=month).get_json()["bookings"]]
            self.assertTrue(any(s.startswith(last.isoformat()) for s in ids), month)

    def test_unknown_and_archived_resources(self):
        self.assertEqual(self.get(self.student, rid=9999).status_code, 404)
        archived = self.db.add_resource("Old Saw", archived=1)
        self.assertEqual(self.get(self.student, rid=archived).status_code, 404)
        self.assertEqual(self.get(self.admin, rid=archived).status_code, 200)

    def test_bad_month_is_400(self):
        for month in ("2026-13", "nope", "2026", "1999-01"):
            self.assertEqual(self.get(self.student, month=month).status_code, 400, month)

    def test_default_month_is_this_month(self):
        r = self.call("get", f"/api/calendar/resource/{self.rid}", self.student)
        self.assertEqual(r.get_json()["month"], datetime.date.today().strftime("%Y-%m"))
