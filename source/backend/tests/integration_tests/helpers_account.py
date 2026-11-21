import datetime
import re
import integration_tests.base as _m

class RealMySQLTestsBaseRequestResetReset:
    def request_reset(self, email="alice@ku.th"):
        from middleware.rate_limit import reset_rate_limits

        reset_rate_limits()
        before = len(self.mails)
        r = self.client.post("/api/auth/forgot-password", json={"email": email})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(self.mails), before + 1, "no reset e-mail was produced")
        return re.search(r"reset_token=([\w-]+)", self.mails[-1][1]).group(1)

    def reset(self, token, password):
        return self.client.post("/api/auth/reset-password", json={"token": token, "password": password})

    def login(self, password, email="alice@ku.th"):
        return self.client.post("/api/auth/login", json={"email": email, "password": password})

    # Google linking
    def google(self, sub, email="alice@ku.th"):
        payload = {"sub": sub, "email": email, "email_verified": True, "name": "Alice"}
        with _m.mock.patch(_m.VERIFY, return_value=payload):
            return self.client.post("/api/auth/google", json={"credential": "tok"})

    # booking / archive SQL on the real engine
    def _resource(self, status="Available", code="RES-0001"):
        return self.sql(
            "INSERT INTO resources (resource_code, name, type, category, location, owner, status) "
            "VALUES (%s, 'Printer', 'Equipment', 'Fab', 'Lab A', 'Admin', %s)", (code, status))

    def _booking(self, rid, uid, start, end, status="Approved", checked_in=None, checked_out=None):
        return self.sql(
            "INSERT INTO bookings (resource_id, requester_id, start_time, end_time, purpose, status, "
            "checked_in_at, checked_out_at) VALUES (%s, %s, %s, %s, 'x', %s, %s, %s)",
            (rid, uid, start, end, status, checked_in, checked_out))

    def _create(self, rid, uid, start, hours=1):
        from models.booking.model import BookingModel

        return BookingModel.create({"resource_id": rid, "start_time": start.isoformat(),
                                    "end_time": (start + datetime.timedelta(hours=hours)).isoformat(),
                                    "purpose": "Test"}, requester_id=uid)
