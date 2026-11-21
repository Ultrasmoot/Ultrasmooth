from resource_tests.base import (
    DbTestCase,
    ResourceDetailPageTestsBase,
) 


class ResourceDetailFieldTests(DbTestCase):
    BASE = {"name": "Meeting Room A", "type": "Room", "category": "Rooms", "location": "Room 301", "owner": "Admin"}

    def create(self, **extra):
        return self.call("post", "/api/resources", self.admin, {**self.BASE, **extra})

    def test_details_are_saved_and_returned(self):
        r = self.create(building="Building 15", floor="3rd floor", capacity=30,
                        features=["Projector", "Whiteboard", "Power outlets", "Air conditioning"],
                        usage_notes="Seminars and group meetings.")
        self.assertEqual(r.status_code, 201, r.get_json())
        res = r.get_json()["resource"]
        self.assertEqual((res["building"], res["floor"], res["capacity"]), ("Building 15", "3rd floor", 30))
        self.assertEqual(res["features"], ["Projector", "Whiteboard", "Power outlets", "Air conditioning"])
        self.assertEqual(res["usage_notes"], "Seminars and group meetings.")
        listed = self.call("get", "/api/resources", self.student).get_json()["resources"][0]
        self.assertEqual(listed["capacity"], 30)

    def test_every_detail_is_optional(self):
        res = self.create().get_json()["resource"]
        self.assertEqual((res["building"], res["floor"], res["capacity"], res["features"], res["usage_notes"]),
                         (None, None, None, [], None))

    def test_features_given_as_text_are_cleaned(self):
        res = self.create(features=" Projector, Wi-Fi ,projector,,  Wi-Fi ").get_json()["resource"]
        self.assertEqual(res["features"], ["Projector", "Wi-Fi"]) # trimmed, no blanks, no duplicates

    def test_invalid_details_are_400_and_nothing_is_saved(self):
        bad = [{"capacity": 0}, {"capacity": -3}, {"capacity": "abc"}, {"capacity": True}, {"capacity": 12.5},
               {"capacity": 10 ** 6}, {"capacity": [5]}, {"building": 5}, {"building": "x" * 101}, {"floor": "x" * 51},
               {"usage_notes": "x" * 1001}, {"usage_notes": ["a"]}, {"features": 5}, {"features": [1, 2]},
               {"features": ["a,b"]}, {"features": ["x" * 41]}, {"features": [f"f{i}" for i in range(16)]},
               {"features": ["x" * 40] * 1 + [f"{i:0>38}" for i in range(14)]}]
        for extra in bad:
            r = self.create(**extra)
            self.assertEqual(r.status_code, 400, extra)
        self.assertEqual(self.db.one("SELECT COUNT(*) AS n FROM resources")["n"], 0)

    def test_update_touches_only_what_was_sent_and_can_clear(self):
        rid = self.create(building="Building 15", capacity=30, features=["Projector"]).get_json()["resource"]["id"]
        r = self.call("put", f"/api/resources/{rid}", self.admin, {"capacity": 40})
        res = r.get_json()["resource"]
        self.assertEqual((res["capacity"], res["building"], res["features"]), (40, "Building 15", ["Projector"]))
        res = self.call("put", f"/api/resources/{rid}", self.admin, {"capacity": None, "building": "  ", "features": []}).get_json()["resource"]
        self.assertEqual((res["capacity"], res["building"], res["features"]), (None, None, []))
        self.assertEqual(self.call("put", f"/api/resources/{rid}", self.admin, {"capacity": "x"}).status_code, 400)

    def test_only_admin_can_change_details(self):
        rid = self.create().get_json()["resource"]["id"]
        for uid in (self.student, self.professor):
            self.assertEqual(self.call("put", f"/api/resources/{rid}", uid, {"capacity": 5}).status_code, 403)
            self.assertEqual(self.call("post", "/api/resources", uid, {**self.BASE, "capacity": 5}).status_code, 403)


class ResourceDetailPageTests_1(ResourceDetailPageTestsBase):
    def test_login_required_and_unknown_is_404(self):
        self.assertEqual(self.detail(None).status_code, 401)
        self.assertEqual(self.detail(self.student, 9999).status_code, 404)
