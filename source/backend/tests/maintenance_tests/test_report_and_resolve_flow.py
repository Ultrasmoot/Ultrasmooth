# Part 2 of the tests in test_maintenance.py
from support.stubs.maintenance_base import ReportAndResolveFlowTestsBase
from support.stubs.checkin_sql_write import ADMIN, PRINTER, SCOPE, STUDENT
from models.booking.model import ValidationError as BookingError
from models.booking.model import BookingModel
import datetime


class ReportAndResolveFlowTests_2(ReportAndResolveFlowTestsBase):
    def test_confirm_twice_is_rejected(self):
        rid = self.report(STUDENT).get_json()["record"]["id"]
        self.act(rid, "confirm")
        r = self.act(rid, "confirm")
        self.assertEqual(r.status_code, 400)
        self.assertIn("already open", r.get_json()["error"])

    def test_dismiss_leaves_resource_alone_and_locks_the_record(self):
        rid = self.report(STUDENT).get_json()["record"]["id"]
        reason = {"reason": "Not a real fault"}
        record = self.act(rid, "dismiss", json=reason).get_json()["record"]
        self.assertEqual(record["status"], "Dismissed")
        self.assertEqual(record["dismiss_reason"], "Not a real fault")
        self.assertEqual(self.db.status_of(PRINTER), "Available")
        for action in ("confirm", "dismiss", "resolve"):
            self.assertEqual(self.act(rid, action, json=reason).status_code, 400, action)
        self.assertEqual(self.call("put", f"/api/maintenance/{rid}", ADMIN, {"description": "x"}).status_code, 400)

    def test_dismiss_requires_a_reason(self):
        rid = self.report(STUDENT).get_json()["record"]["id"]
        for body in (None, {}, {"reason": "   "}, {"reason": "x" * 256}):
            r = self.act(rid, "dismiss", json=body)
            self.assertEqual(r.status_code, 400, body)
            self.assertIn("reason", r.get_json()["error"])
        self.assertEqual(self.db.records[rid]["status"], "Reported")

    def test_resource_in_maintenance_cannot_be_booked(self):
        self.report(ADMIN)
        start = datetime.datetime.now() + datetime.timedelta(days=1)
        with self.assertRaises(BookingError) as ctx:
            BookingModel.create(
                {"resource_id": PRINTER, "start_time": start.isoformat(),
                 "end_time": (start + datetime.timedelta(hours=2)).isoformat(), "purpose": "print"},
                requester_id=STUDENT,
            )
        self.assertIn("Maintenance", str(ctx.exception))

    def test_reported_but_unconfirmed_issue_does_not_block_booking(self):
        self.report(STUDENT)
        # Booking checks the resource's own status; an unconfirmed report leaves it Available.
        self.assertEqual(self.db.status_of(PRINTER), "Available")

    def test_resolve_returns_resource_to_available(self):
        rid = self.report(ADMIN).get_json()["record"]["id"]
        r = self.act(rid, "resolve")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["record"]["status"], "Resolved")
        self.assertEqual(self.db.status_of(PRINTER), "Available")

    def test_resolve_twice_is_rejected(self):
        rid = self.report(ADMIN).get_json()["record"]["id"]
        self.act(rid, "resolve")
        r = self.act(rid, "resolve")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.db.status_of(PRINTER), "Available")

    def test_cannot_resolve_an_unconfirmed_report(self):
        rid = self.report(STUDENT).get_json()["record"]["id"]
        self.assertEqual(self.act(rid, "resolve").status_code, 400)
        self.assertEqual(self.db.records[rid]["status"], "Reported")

    def test_multiple_open_issues_keep_resource_in_maintenance_until_last_is_resolved(self):
        first = self.report(ADMIN, description="Nozzle jammed").get_json()["record"]["id"]
        second = self.report(ADMIN, description="Belt loose", status="In Progress").get_json()["record"]["id"]
        self.act(first, "resolve")
        self.assertEqual(self.db.status_of(PRINTER), "Maintenance")
        self.act(second, "resolve")
        self.assertEqual(self.db.status_of(PRINTER), "Available")

    def test_pending_report_does_not_hold_resource_in_maintenance(self):
        pending = self.report(STUDENT).get_json()["record"]["id"]
        confirmed = self.report(ADMIN).get_json()["record"]["id"]
        self.act(confirmed, "resolve")
        self.assertEqual(self.db.status_of(PRINTER), "Available")
        self.assertEqual(self.db.records[pending]["status"], "Reported")

    def test_issues_on_different_resources_are_independent(self):
        a = self.report(ADMIN, resource_id=PRINTER).get_json()["record"]["id"]
        self.report(ADMIN, resource_id=SCOPE)
        self.act(a, "resolve")
        self.assertEqual(self.db.status_of(PRINTER), "Available")
        self.assertEqual(self.db.status_of(SCOPE), "Maintenance")

    def test_unknown_record_returns_400_not_500(self):
        self.assertEqual(self.act(999, "resolve").status_code, 400)
        self.assertEqual(self.act(999, "confirm").status_code, 400)
