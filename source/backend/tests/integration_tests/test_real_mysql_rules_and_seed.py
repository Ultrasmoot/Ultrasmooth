from integration_tests.base import (
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
    MIN,
    RealMySQLTestsBase,
    SCHEMA,
    _statements,
) 
import datetime
import os


class RealMySQLTests_2(RealMySQLTestsBase):
    def test_in_use_booking_rules_and_archive_on_real_mysql(self):
        from models.booking.model import ValidationError as BookingError
        from models.resource.model import ResourceModel, ValidationError as ResourceError

        _, student = self.signup()
        _, other = self.signup(email="bob@ku.th", student_id="6512345679")
        now = datetime.datetime.now().replace(microsecond=0)
        rid = self._resource(status="In Use")
        busy = self._booking(rid, other, now - 120 * MIN, now + 120 * MIN, checked_in=now - 100 * MIN)

        with self.assertRaises(BookingError) as ctx:       
            self._create(rid, student, now + 60 * MIN)
        self.assertIn("in use until", str(ctx.exception))
        self.assertEqual(self._create(rid, student, now + 120 * MIN)["status"], "Pending")

        with self.assertRaises(ResourceError) as ctx: 
            ResourceModel.archive(rid)
        self.assertIn("In Use", str(ctx.exception))

        # Checked out: the resource is free again but the live bookings still block archiving.
        self.sql("UPDATE bookings SET checked_out_at = %s WHERE id = %s", (now, busy))
        self.sql("UPDATE resources SET status = 'Available' WHERE id = %s", (rid,))
        with self.assertRaises(ResourceError) as ctx:
            ResourceModel.archive(rid)
        self.assertIn("active bookings", str(ctx.exception))

        # The pending request is rejected and the old booking is long over (a whole day, so the
        # test does not depend on the DB clock and the app clock being in the same time zone).
        self.sql("UPDATE bookings SET status = 'Rejected' WHERE status = 'Pending'")
        self.sql("UPDATE bookings SET start_time = %s, end_time = %s WHERE id = %s",
                 (now - 48 * 60 * MIN, now - 24 * 60 * MIN, busy))
        ResourceModel.archive(rid)
        self.assertEqual(self.sql("SELECT is_archived FROM resources WHERE id = %s", (rid,), fetch=True)[0]["is_archived"], 1)

    def test_demo_seed_loads_and_is_consistent(self):
        # seed.sql runs on the real engine, and a resource is 'In Use' only with a checked-in booking
        import mysql.connector

        seed = os.path.join(os.path.dirname(SCHEMA), "seed.sql")
        conn = mysql.connector.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
                                       database=DB_NAME, autocommit=True)
        try:
            cur = conn.cursor()
            for statement in _statements(seed):
                cur.execute(statement)
        finally:
            conn.close()
        orphans = self.sql(
            """SELECT r.resource_code FROM resources r
               WHERE r.status = 'In Use' AND NOT EXISTS (
                   SELECT 1 FROM bookings b WHERE b.resource_id = r.id AND b.status = 'Approved'
                     AND b.checked_in_at IS NOT NULL AND b.checked_out_at IS NULL)""", fetch=True)
        self.assertEqual(orphans, [], "a resource is In Use without a checked-in booking")
        # Nobody is checked in right after seeding, so every demo resource starts Available
        self.assertEqual(self.sql("SELECT status FROM resources WHERE resource_code = 'RES-0002'", fetch=True)[0]["status"],
                         "Available")
        # The demo check-in booking (RES-0001) is Approved, already started, and not checked in yet.
        demo = self.sql(
            """SELECT b.status, b.checked_in_at FROM bookings b JOIN resources r ON r.id = b.resource_id
               WHERE r.resource_code = 'RES-0001' AND b.status = 'Approved'
                 AND b.start_time <= NOW() AND b.end_time > NOW()""", fetch=True)
        self.assertEqual(len(demo), 1)
        self.assertIsNone(demo[0]["checked_in_at"])
        self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM bookings WHERE status = 'Pending' AND start_time > NOW()",
                                  fetch=True)[0]["n"], 1)
