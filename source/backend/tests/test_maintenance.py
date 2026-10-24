import copy
import datetime
import os
import sys
import unittest
import jwt 
from unittest import mock

os.environ.setdefault("APP_ENV", "development")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  
from config import Config  
from middleware.rate_limit import reset_rate_limits  
from models.booking_model import BookingModel, ValidationError as BookingError 
from models.user_model import UserModel 

ADMIN, STUDENT, OTHER_STUDENT, PROFESSOR = 1, 2, 3, 4
PRINTER, SCOPE, ARCHIVED = 10, 11, 12


def _norm(sql):
    return " ".join(sql.split()).lower()


class FakeDB:
    """In-memory stand-in for the MySQL tables these tests touch."""

    def __init__(self):
        self.users = {
            ADMIN: {"id": ADMIN, "full_name": "Demo Admin", "email": "admin@ku.th", "role": "admin", "is_active": 1},
            STUDENT: {"id": STUDENT, "full_name": "Demo Student", "email": "s1@ku.th", "role": "undergrad_student", "is_active": 1},
            OTHER_STUDENT: {"id": OTHER_STUDENT, "full_name": "Other Student", "email": "s2@ku.th", "role": "phd_student", "is_active": 1},
            PROFESSOR: {"id": PROFESSOR, "full_name": "Aj. Somchai", "email": "p@ku.th", "role": "professor", "is_active": 1},
        }

        def res(rid, name, archived=0):
            return {"id": rid, "resource_code": f"RES-{rid:04d}", "name": name, "type": "Equipment",
                    "category": "Fabrication", "location": "Lab A", "owner": "Demo Admin",
                    "status": "Available", "is_archived": archived}

        self.resources = {PRINTER: res(PRINTER, "3D Printer"), SCOPE: res(SCOPE, "Oscilloscope"),
                          ARCHIVED: res(ARCHIVED, "Old Scanner", archived=1)}
        self.records = {}
        self._next = 1
        self._clock = datetime.datetime(2026, 10, 1, 9, 0, 0)

    def connection(self):
        return FakeConn(self)

    def status_of(self, rid):
        return self.resources[rid]["status"]


class FakeConn:
    def __init__(self, db):
        self.db = db
        self._snap = (copy.deepcopy(db.resources), copy.deepcopy(db.records))

    def cursor(self, dictionary=False):
        return FakeCursor(self.db)

    def commit(self):
        self._snap = (copy.deepcopy(self.db.resources), copy.deepcopy(self.db.records))

    def rollback(self):
        self.db.resources, self.db.records = copy.deepcopy(self._snap[0]), copy.deepcopy(self._snap[1])

    def close(self):
        pass


class FakeCursor:
    def __init__(self, db):
        self.db = db
        self._rows = []
        self.lastrowid = None
        self.rowcount = 0

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def _joined(self, rec):
        out = dict(rec)
        out["resource_name"] = self.db.resources[rec["resource_id"]]["name"]
        out["resource_code"] = self.db.resources[rec["resource_id"]]["resource_code"]
        out["reporter_name"] = self.db.users[rec["reported_by"]]["full_name"]
        out["reporter_email"] = self.db.users[rec["reported_by"]]["email"]
        return out

    def execute(self, sql, params=()):
        db, q, p = self.db, _norm(sql), list(params or ())
        self._rows, self.rowcount = [], 0
        # Like MySQL: only an INSERT sets lastrowid; any other statement (such as an
        # UPDATE) resets it to 0. The model must read it right after its INSERT.
        if not q.startswith("insert"):
            self.lastrowid = 0

        if q.startswith("select resource_id from maintenance_records where id"):
            r = db.records.get(p[0])
            self._rows = [{"resource_id": r["resource_id"]}] if r else []
        elif q.startswith("select id, status, is_archived from resources where id"):
            r = db.resources.get(p[0])
            self._rows = [{k: r[k] for k in ("id", "status", "is_archived")}] if r else []
        elif q.startswith("select status, is_archived from resources where id"):
            r = db.resources.get(p[0])
            self._rows = [{k: r[k] for k in ("status", "is_archived")}] if r else []
        elif q.startswith("select id, status from resources where id"):
            r = db.resources.get(p[0])
            self._rows = [{"id": r["id"], "status": r["status"]}] if r else []
        elif q.startswith("select * from resources where id"):
            r = db.resources.get(p[0])
            self._rows = [dict(r)] if r else []
        elif q.startswith("select * from maintenance_records where id"):
            r = db.records.get(p[0])
            self._rows = [dict(r)] if r else []
        elif q.startswith("select count(*) as n from maintenance_records"):
            exclude = p[1] if len(p) > 1 else None
            n = sum(1 for r in db.records.values()
                    if r["resource_id"] == p[0] and r["status"] in ("Open", "In Progress") and r["id"] != exclude)
            self._rows = [{"n": n}]
        elif "from maintenance_records m join resources r" in q:
            rows = list(db.records.values())
            if "where m.id = %s" in q:
                rows = [r for r in rows if r["id"] == p[0]]
            else:
                if "m.reported_by = %s" in q:
                    owner = p.pop(0)
                    rows = [r for r in rows if r["reported_by"] == owner]
                if "m.status in" in q:
                    rows = [r for r in rows if r["status"] in p]
                rows.sort(key=lambda r: (r["created_at"], r["id"]), reverse=True)
            self._rows = [self._joined(r) for r in rows]
        elif q.startswith("insert into maintenance_records"):
            rid = db._next
            db._next += 1
            db._clock += datetime.timedelta(minutes=1)
            if "confirmed_by" in q:  # admin report: confirmed immediately
                res_id, by, desc, status, day, conf = p
                rec_status, confirmed_by, confirmed_at = status, conf, db._clock
            else:  # non-admin report: waits for an admin
                res_id, by, desc, day = p
                rec_status, confirmed_by, confirmed_at = "Reported", None, None
            db.records[rid] = {"id": rid, "resource_id": res_id, "reported_by": by, "description": desc,
                               "status": rec_status, "issue_date": day, "confirmed_by": confirmed_by,
                               "confirmed_at": confirmed_at, "closed_by": None, "closed_at": None,
                               "created_at": db._clock}
            self.lastrowid = rid
        elif q.startswith("update resources set status = 'maintenance'"):
            db.resources[p[0]]["status"] = "Maintenance"
        elif q.startswith("update resources set status = 'available'"):
            db.resources[p[0]]["status"] = "Available"
        elif q.startswith("update resources set status=%s where id=%s and status <> 'maintenance'"):
            r = db.resources[p[1]]
            if r["status"] != "Maintenance":
                r["status"] = p[0]
                self.rowcount = 1
        elif q.startswith("update resources set name=%s"):
            r = db.resources[p[5]]
            r["name"], r["type"], r["category"], r["location"], r["owner"] = p[:5]
        elif q.startswith("update maintenance_records set status = 'open'"):
            r = db.records[p[1]]
            r.update(status="Open", confirmed_by=p[0], confirmed_at=db._clock)
        elif q.startswith("update maintenance_records set status = 'dismissed'"):
            db.records[p[2]].update(status="Dismissed", dismiss_reason=p[0], closed_by=p[1], closed_at=db._clock)
        elif q.startswith("update maintenance_records set status = 'resolved'") and "where resource_id" in q:
            # "Return to Available": every Open / In Progress issue of one resource
            closed_by, resource_id = p
            for r in db.records.values():
                if r["resource_id"] == resource_id and r["status"] in ("Open", "In Progress"):
                    r.update(status="Resolved", closed_by=closed_by, closed_at=db._clock)
                    self.rowcount += 1
        elif q.startswith("update maintenance_records set status = 'resolved'"):
            db.records[p[1]].update(status="Resolved", closed_by=p[0], closed_at=db._clock)
        elif q.startswith("update resources set is_archived = 0 where id"):
            db.resources[p[0]]["is_archived"] = 0
        elif q.startswith("update maintenance_records set description=%s, status=%s, issue_date=%s"):
            db.records[p[3]].update(description=p[0], status=p[1], issue_date=p[2])
        else:
            raise AssertionError(f"FakeDB does not understand SQL: {q}")


def _token(user_id):
    # Same claim _issue_token adds; the fake users have no password_hash.
    from middleware.auth_middleware import password_fingerprint

    return jwt.encode(
        {"sub": str(user_id), "pwf": password_fingerprint(None)},
        Config.SECRET_KEY,
        algorithm="HS256",
    )


class MaintenanceTestBase(unittest.TestCase):
    def setUp(self):
        reset_rate_limits()
        self.db = FakeDB()
        for target in ("models.maintenance_model.get_connection",
                       "models.booking_model.get_connection",
                       "models.resource_model.get_connection"):
            patcher = mock.patch(target, side_effect=self.db.connection)
            patcher.start()
            self.addCleanup(patcher.stop)
        finder = mock.patch.object(UserModel, "find_by_id",
                                   side_effect=lambda uid: self.db.users.get(int(uid)))
        finder.start()
        self.addCleanup(finder.stop)
        self.client = create_app().test_client()

    # --- helpers ---
    def call(self, method, path, user=None, json=None):
        headers = {"Authorization": f"Bearer {_token(user)}"} if user else {}
        return getattr(self.client, method)(path, json=json, headers=headers)

    def report(self, user, resource_id=PRINTER, description="Nozzle is jammed", **extra):
        body = {"resource_id": resource_id, "description": description,
                "date": datetime.date.today().isoformat(), **extra}
        return self.call("post", "/api/maintenance", user, body)

    def act(self, record_id, action, user=ADMIN, json=None):
        return self.call("post", f"/api/maintenance/{record_id}/{action}", user, json)


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


class ReportAndResolveFlowTests(MaintenanceTestBase):
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
        with mock.patch("models.resource_model.ResourceModel.get",
                        side_effect=[stale_existing, dict(self.db.resources[PRINTER])]):
            r = self.call("put", f"/api/resources/{PRINTER}", ADMIN, self.resource_body(status="Available"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.db.status_of(PRINTER), "Maintenance")


class LastRowIdRegressionTests(MaintenanceTestBase):
    def test_admin_report_returns_the_record_it_saved(self):
        # Regression: the admin path runs an UPDATE on the resource after the INSERT.
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
        with mock.patch("models.maintenance_model.MaintenanceModel.list", side_effect=RuntimeError("secret detail")):
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


if __name__ == "__main__":
    unittest.main()