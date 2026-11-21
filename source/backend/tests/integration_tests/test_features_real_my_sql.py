from integration_tests.base_features import (
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
    FeaturesRealMySQLTestsBase,
    SCHEMA,
) 
import datetime
import os


class FeaturesRealMySQLTests_1(FeaturesRealMySQLTestsBase):
    def test_booking_flow_writes_the_log_and_the_notifications_in_one_go(self):
        rid = self.call("post", "/api/resources", self.admin, {"name": "3D Printer", "type": "Equipment",
                        "category": "Fabrication", "location": "Lab", "owner": "Admin"}).get_json()["resource"]["id"]
        start = self.when(2, 10)
        r = self.call("post", "/api/bookings", self.student, {"resource_id": rid, "start_time": start.isoformat(),
                      "end_time": (start + datetime.timedelta(hours=2)).isoformat(), "purpose": "Print"})
        self.assertEqual(r.status_code, 201, r.get_json())
        bid = r.get_json()["booking"]["id"]
        self.assertEqual(self.call("post", f"/api/bookings/{bid}/decide", self.admin,
                                   {"decision": "reject", "reason": "Class that day"}).status_code, 200)
        log = self.call("get", "/api/activity?per_page=5&page=1", self.professor).get_json()
        self.assertEqual([i["action"] for i in log["items"]], ["booking.rejected", "booking.submitted", "resource.created"])
        self.assertEqual(len(self.call("get", f"/api/activity?user={self.student}", self.admin).get_json()["items"]), 1)
        mine = self.call("get", "/api/notifications", self.student).get_json()
        self.assertEqual((mine["unread"], mine["notifications"][0]["title"]), (1, "Booking declined"))
        self.assertEqual(self.call("get", "/api/notifications", self.admin).get_json()["notifications"][0]["title"], "New booking request")

    def test_dashboard_and_resource_detail_queries_run_on_mysql(self):
        rid = self.call("post", "/api/resources", self.admin, {"name": "Laser Cutter", "type": "Equipment",
                        "category": "Fabrication", "location": "Lab", "owner": "Admin"}).get_json()["resource"]["id"]
        now = datetime.datetime.now()
        self.sql("INSERT INTO bookings (resource_id, requester_id, start_time, end_time, purpose, status) "
                 "VALUES (%s, %s, %s, %s, 'Cut', 'Approved')", (rid, self.student, now - datetime.timedelta(hours=1), now + datetime.timedelta(hours=1)))
        dash = self.call("get", "/api/dashboard?days=7", self.professor).get_json()
        self.assertEqual((dash["resources"]["total"], dash["bookings"]["active"]), (1, 1))
        self.assertEqual(dash["utilization"][0]["category"], "Fabrication")
        self.assertEqual(self.call("get", "/api/dashboard", self.student).status_code, 403)
        detail = self.call("get", f"/api/resources/{rid}/detail", self.admin).get_json()
        self.assertEqual(detail["schedule"][0]["requester_name"], "Demo Student")
        self.assertEqual(self.call("get", f"/api/resources/{rid}/detail", self.student).get_json()["schedule"][0].keys(),
                         {"start_time", "end_time"})

    def test_demo_seed_loads(self):
        # seed.sql is MySQL, so this is the only place it can be checked
        import mysql.connector

        lines = [ln for ln in open(os.path.join(os.path.dirname(SCHEMA), "seed.sql"), encoding="utf-8").read().splitlines()
                 if not ln.strip().startswith("--")]
        conn = mysql.connector.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
                                       database=DB_NAME, autocommit=True)
        try:
            cur = conn.cursor()
            for statement in [s.strip() for s in "\n".join(lines).split(";") if s.strip()]:
                cur.execute(statement)
        finally:
            conn.close()
        professors = self.call("get", "/api/appointments/professors", self.sql(
            "SELECT id FROM users WHERE email = 'student@ku.th'", fetch=True)[0]["id"]).get_json()["professors"]
        self.assertGreaterEqual(len(professors), 5)
        self.assertTrue(all(p["expertise"] for p in professors))
        self.assertGreaterEqual(self.sql("SELECT COUNT(*) AS n FROM activity_log", fetch=True)[0]["n"], 7)
