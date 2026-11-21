# history access, filters and pagination tests
from history_tests.base import (
    DbTestCase,
    ago,
)  # noqa: F401


class HistoryTests(DbTestCase):
    def setUp(self):
        super().setUp()
        self.printer = self.db.add_resource("3D Printer")
        self.laser = self.db.add_resource("Laser Cutter")
        # in use, done 5h ago, done 30h ago
        self.in_use = self.db.add_booking(self.laser, self.other, ago(3), ago(-1), checked_in_at=ago(2))
        self.done = self.db.add_booking(self.printer, self.student, ago(6), ago(4),
                                        checked_in_at=ago(5), checked_out_at=ago(4))
        self.old = self.db.add_booking(self.printer, self.other, ago(31), ago(29),
                                       checked_in_at=ago(30), checked_out_at=ago(29))
        # not checked in
        self.db.add_booking(self.printer, self.student, ago(-5), ago(-4))

    def get(self, qs="", uid=None):
        return self.call("get", "/api/history" + qs, uid or self.admin)

    # access control
    def test_only_admin_can_read(self):
        for uid in (self.student, self.professor, self.other):
            self.assertEqual(self.get(uid=uid).status_code, 403)
            self.assertEqual(self.call("get", "/api/history/meta", uid).status_code, 403)
        self.assertEqual(self.call("get", "/api/history").status_code, 401)

    # history results
    def test_newest_first_and_only_checked_in(self):
        body = self.get().get_json()
        self.assertEqual([r["id"] for r in body["items"]], [self.in_use, self.done, self.old])
        self.assertEqual(body["total"], 3)

    def test_status_in_use_or_done(self):
        items = {r["id"]: r for r in self.get().get_json()["items"]}
        self.assertEqual(items[self.in_use]["status"], "In use")
        self.assertIsNone(items[self.in_use]["checked_out_at"])
        self.assertEqual(items[self.done]["status"], "Done")
        self.assertEqual(items[self.done]["user_name"], "Demo Student")

    # filters pagination
    def test_filter_by_user_and_resource(self):
        ids = lambda qs: [r["id"] for r in self.get(qs).get_json()["items"]]  # noqa: E731
        self.assertEqual(ids(f"?user={self.other}"), [self.in_use, self.old])
        self.assertEqual(ids(f"?resource={self.printer}"), [self.done, self.old])
        self.assertEqual(ids(f"?user={self.other}&resource={self.printer}"), [self.old])

    def test_filter_by_date_is_inclusive(self):
        day = (ago(30)).date().isoformat()
        ids = [r["id"] for r in self.get(f"?from={day}&to={day}").get_json()["items"]]
        self.assertEqual(ids, [self.old])

    def test_paging(self):
        body = self.get("?per_page=2&page=2").get_json()
        self.assertEqual((len(body["items"]), body["pages"], body["total"]), (1, 2, 3))
        self.assertEqual(body["items"][0]["id"], self.old)

    def test_bad_filters_are_400(self):
        for qs in ("?from=nope", "?user=abc", "?resource=0", "?page=0", "?per_page=1000",
                   "?from=2026-05-02&to=2026-05-01"):
            self.assertEqual(self.get(qs).status_code, 400, qs)

    def test_meta_lists_people_and_resources_who_appear(self):
        meta = self.call("get", "/api/history/meta", self.admin).get_json()
        self.assertEqual(sorted(u["name"] for u in meta["users"]), ["Demo Student", "Other Student"])
        self.assertEqual(sorted(r["name"] for r in meta["resources"]), ["3D Printer", "Laser Cutter"])