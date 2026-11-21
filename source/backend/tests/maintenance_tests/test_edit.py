# Part 3 of the tests in test_maintenance.py
from support.stubs.maintenance_base import MaintenanceTestBase
from support.stubs.checkin_sql_write import ADMIN, OTHER_STUDENT, PRINTER, PROFESSOR, SCOPE, STUDENT
from unittest import mock
from support.stubs.checkin_sql_write import ARCHIVED


class EditTests(MaintenanceTestBase):
    def test_admin_can_edit_description_and_status_of_open_record(self):
        rid = self.report(ADMIN).get_json()["record"]["id"]
        r = self.call("put", f"/api/maintenance/{rid}", ADMIN, {"description": "Replaced nozzle", "status": "In Progress"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["record"]["description"], "Replaced nozzle")
        self.assertEqual(r.get_json()["record"]["status"], "In Progress")
        self.assertEqual(self.db.status_of(PRINTER), "Maintenance")

    def test_edit_validation(self):
        rid = self.report(ADMIN).get_json()["record"]["id"]
        for body in ({"description": ""}, {"description": "x" * 501}, {"status": "Resolved"}, {"status": "Reported"}):
            self.assertEqual(self.call("put", f"/api/maintenance/{rid}", ADMIN, body).status_code, 400, body)
        self.assertEqual(self.db.records[rid]["description"], "Nozzle is jammed")

    def test_resource_cannot_be_changed_by_edit(self):
        rid = self.report(ADMIN).get_json()["record"]["id"]
        r = self.call("put", f"/api/maintenance/{rid}", ADMIN, {"resource_id": SCOPE})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.db.records[rid]["resource_id"], PRINTER)

    def test_resolved_record_is_locked(self):
        rid = self.report(ADMIN).get_json()["record"]["id"]
        self.act(rid, "resolve")
        r = self.call("put", f"/api/maintenance/{rid}", ADMIN, {"description": "late edit"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.db.records[rid]["description"], "Nozzle is jammed")


class ResourceApiGuardTests(MaintenanceTestBase):
    """The Resource API must not be a back door to the Maintenance status."""

    def resource_body(self, **extra):
        return {"name": "3D Printer", "type": "Equipment", "category": "Fabrication",
                "location": "Lab A", "owner": "Demo Admin", **extra}

    def test_cannot_create_a_resource_in_maintenance(self):
        r = self.call("post", "/api/resources", ADMIN, self.resource_body(status="Maintenance"))
        self.assertEqual(r.status_code, 400)
        self.assertIn("Maintenance", r.get_json()["error"])

    def test_cannot_move_a_resource_into_maintenance(self):
        r = self.call("put", f"/api/resources/{PRINTER}", ADMIN, self.resource_body(status="Maintenance"))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.db.status_of(PRINTER), "Available")

    def test_cannot_move_a_resource_out_of_maintenance(self):
        self.report(ADMIN)
        for status in ("Available", "In Use"):
            r = self.call("put", f"/api/resources/{PRINTER}", ADMIN, self.resource_body(status=status))
            self.assertEqual(r.status_code, 400, status)
        self.assertEqual(self.db.status_of(PRINTER), "Maintenance")

    def test_editing_other_fields_of_a_maintenance_resource_still_works(self):
        self.report(ADMIN)
        r = self.call("put", f"/api/resources/{PRINTER}", ADMIN,
                      self.resource_body(name="3D Printer (renamed)", status="Maintenance"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.db.resources[PRINTER]["name"], "3D Printer (renamed)")
        self.assertEqual(self.db.status_of(PRINTER), "Maintenance")

    def test_available_and_in_use_can_still_be_switched(self):
        r = self.call("put", f"/api/resources/{PRINTER}", ADMIN, self.resource_body(status="In Use"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.db.status_of(PRINTER), "In Use")

    def test_edit_form_resending_old_status_cannot_undo_a_new_maintenance(self):
        # The edit form was opened while the resource was Available; meanwhile an
        # admin confirmed an issue. Saving the stale form must not clear Maintenance.
        stale_existing = dict(self.db.resources[PRINTER])
        self.report(ADMIN)
        with mock.patch("models.resource.model.ResourceModel.get",
                        side_effect=[stale_existing, dict(self.db.resources[PRINTER])]):
            r = self.call("put", f"/api/resources/{PRINTER}", ADMIN, self.resource_body(status="Available"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.db.status_of(PRINTER), "Maintenance")


class LastRowIdRegressionTests(MaintenanceTestBase):
    def test_admin_report_returns_the_record_it_saved(self):
        # Regression: the admin path runs an UPDATE on the resource after the INSERT.
        # MySQL resets lastrowid to 0 on that UPDATE, so reading it afterwards made the
        # saved record "not found" and the request failed with a 500.
        r = self.report(ADMIN)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()["record"]["id"], max(self.db.records))
        self.assertEqual(self.db.status_of(PRINTER), "Maintenance")


class ReturnToAvailableTests(MaintenanceTestBase):
    def restore(self, user=ADMIN, resource_id=PRINTER):
        return self.call("post", f"/api/resources/{resource_id}/restore", user)

    def test_login_required_and_admin_only(self):
        self.report(ADMIN)
        self.assertEqual(self.restore(None).status_code, 401)
        for user in (STUDENT, OTHER_STUDENT, PROFESSOR):
            self.assertEqual(self.restore(user).status_code, 403, user)
        self.assertEqual(self.db.status_of(PRINTER), "Maintenance")

    def test_resolves_every_open_issue_and_frees_the_resource(self):
        first = self.report(ADMIN).get_json()["record"]["id"]
        second = self.report(ADMIN, description="Bed is not level", status="In Progress").get_json()["record"]["id"]
        r = self.restore()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["closed_issues"], 2)
        self.assertEqual(r.get_json()["resource"]["status"], "Available")
        self.assertEqual(self.db.status_of(PRINTER), "Available")
        for rid in (first, second):
            self.assertEqual(self.db.records[rid]["status"], "Resolved")
            self.assertEqual(self.db.records[rid]["closed_by"], ADMIN)

    def test_unreviewed_reports_are_left_alone(self):
        waiting = self.report(STUDENT).get_json()["record"]["id"]
        self.report(ADMIN)
        r = self.restore()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["closed_issues"], 1)
        self.assertEqual(self.db.records[waiting]["status"], "Reported")

    def test_only_works_on_a_resource_in_maintenance(self):
        r = self.restore()
        self.assertEqual(r.status_code, 400)
        self.assertIn("not in Maintenance", r.get_json()["error"])

    def test_unknown_resource_is_rejected(self):
        r = self.restore(resource_id=9999)
        self.assertEqual(r.status_code, 400)
        self.assertIn("not found", r.get_json()["error"])


class UnarchiveTests(MaintenanceTestBase):
    def unarchive(self, user=ADMIN, resource_id=ARCHIVED):
        return self.call("post", f"/api/resources/{resource_id}/unarchive", user)

    def test_admin_can_unarchive(self):
        r = self.unarchive()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.db.resources[ARCHIVED]["is_archived"], 0)

    def test_login_required_and_admin_only(self):
        self.assertEqual(self.unarchive(None).status_code, 401)
        for user in (STUDENT, PROFESSOR):
            self.assertEqual(self.unarchive(user).status_code, 403, user)
        self.assertEqual(self.db.resources[ARCHIVED]["is_archived"], 1)

    def test_unknown_resource_is_rejected(self):
        self.assertEqual(self.unarchive(resource_id=9999).status_code, 400)


class ApiErrorHandlerTests(MaintenanceTestBase):
    def test_unexpected_error_on_an_api_route_returns_json(self):
        with mock.patch("models.maintenance.model.MaintenanceModel.list", side_effect=RuntimeError("secret detail")):
            r = self.call("get", "/api/maintenance", ADMIN)
        self.assertEqual(r.status_code, 500)
        self.assertTrue(r.is_json)
        self.assertIn("Something went wrong", r.get_json()["error"])
        self.assertNotIn("secret detail", r.get_data(as_text=True))

    def test_unknown_api_route_returns_json_404(self):
        r = self.call("get", "/api/does-not-exist", ADMIN)
        self.assertEqual(r.status_code, 404)
        self.assertTrue(r.is_json)
        self.assertIn("error", r.get_json())
