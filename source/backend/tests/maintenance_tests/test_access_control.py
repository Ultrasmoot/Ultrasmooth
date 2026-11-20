# Part 1 of the tests in test_maintenance.py
from support.stubs.maintenance_base import MaintenanceTestBase, ReportAndResolveFlowTestsBase
from support.stubs.checkin_sql_write import ADMIN, ARCHIVED, OTHER_STUDENT, PRINTER, PROFESSOR, SCOPE, STUDENT
import datetime


class AccessControlTests(MaintenanceTestBase):
    def test_login_required_everywhere(self):
        self.assertEqual(self.call("post", "/api/maintenance", None, {}).status_code, 401)
        self.assertEqual(self.call("get", "/api/maintenance").status_code, 401)
        self.assertEqual(self.act(1, "confirm", None).status_code, 401)

    def test_every_role_may_report_but_resource_is_untouched(self):
        for user in (STUDENT, OTHER_STUDENT, PROFESSOR):
            r = self.report(user)
            self.assertEqual(r.status_code, 201)
            self.assertEqual(r.get_json()["record"]["status"], "Reported")
        self.assertEqual(self.db.status_of(PRINTER), "Available")

    def test_non_admin_cannot_confirm_dismiss_resolve_or_edit(self):
        rid = self.report(STUDENT).get_json()["record"]["id"]
        for user in (STUDENT, PROFESSOR):
            for action in ("confirm", "dismiss", "resolve"):
                self.assertEqual(self.act(rid, action, user).status_code, 403, (user, action))
            self.assertEqual(self.call("put", f"/api/maintenance/{rid}", user, {"description": "x"}).status_code, 403)
        self.assertEqual(self.db.records[rid]["status"], "Reported")

    def test_non_admin_sees_only_own_reports(self):
        mine = self.report(STUDENT).get_json()["record"]["id"]
        theirs = self.report(OTHER_STUDENT, resource_id=SCOPE).get_json()["record"]["id"]
        ids = [r["id"] for r in self.call("get", "/api/maintenance", STUDENT).get_json()["records"]]
        self.assertEqual(ids, [mine])
        self.assertEqual(self.call("get", f"/api/maintenance/{theirs}", STUDENT).status_code, 404)
        self.assertEqual(self.call("get", f"/api/maintenance/{mine}", STUDENT).status_code, 200)
        admin_ids = {r["id"] for r in self.call("get", "/api/maintenance", ADMIN).get_json()["records"]}
        self.assertEqual(admin_ids, {mine, theirs})


class ReportValidationTests(MaintenanceTestBase):
    def assert_rejected(self, response, fragment):
        self.assertEqual(response.status_code, 400)
        self.assertIn(fragment, response.get_json()["error"])
        self.assertEqual(self.db.records, {})
        self.assertEqual(self.db.status_of(PRINTER), "Available")

    def test_missing_or_blank_description(self):
        self.assert_rejected(self.report(ADMIN, description=""), "description is required")
        self.assert_rejected(self.report(ADMIN, description="   "), "description is required")

    def test_description_too_long(self):
        self.assert_rejected(self.report(ADMIN, description="x" * 501), "at most 500")

    def test_missing_invalid_or_future_date(self):
        base = {"resource_id": PRINTER, "description": "broken"}
        self.assert_rejected(self.call("post", "/api/maintenance", ADMIN, base), "date is required")
        self.assert_rejected(self.call("post", "/api/maintenance", ADMIN, {**base, "date": "not-a-date"}), "valid date")
        future = (datetime.date.today() + datetime.timedelta(days=2)).isoformat()
        self.assert_rejected(self.call("post", "/api/maintenance", ADMIN, {**base, "date": future}), "future")

    def test_bad_status_for_admin_report(self):
        self.assert_rejected(self.report(ADMIN, status="Resolved"), "status must be")

    def test_unknown_missing_or_archived_resource(self):
        self.assert_rejected(self.report(ADMIN, resource_id=999), "does not exist")
        self.assert_rejected(self.report(ADMIN, resource_id=ARCHIVED), "does not exist")
        self.assert_rejected(self.report(ADMIN, resource_id="abc"), "valid resource")
        self.assert_rejected(self.call("post", "/api/maintenance", ADMIN,
                                       {"description": "x", "date": datetime.date.today().isoformat()}),
                             "valid resource")

    def test_past_date_is_allowed(self):
        r = self.report(ADMIN, date="2026-01-15")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()["record"]["issue_date"], "2026-01-15")


class ReportAndResolveFlowTests_1(ReportAndResolveFlowTestsBase):
    def test_admin_report_puts_resource_into_maintenance_immediately(self):
        r = self.report(ADMIN)
        self.assertEqual(r.status_code, 201)
        record = r.get_json()["record"]
        self.assertEqual(record["status"], "Open")
        self.assertEqual(self.db.status_of(PRINTER), "Maintenance")

    def test_admin_may_report_as_in_progress(self):
        self.assertEqual(self.report(ADMIN, status="In Progress").get_json()["record"]["status"], "In Progress")
        self.assertEqual(self.db.status_of(PRINTER), "Maintenance")

    def test_confirming_a_report_moves_resource_to_maintenance(self):
        rid = self.report(STUDENT).get_json()["record"]["id"]
        self.assertEqual(self.db.status_of(PRINTER), "Available")
        r = self.act(rid, "confirm")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["record"]["status"], "Open")
        self.assertEqual(self.db.status_of(PRINTER), "Maintenance")
