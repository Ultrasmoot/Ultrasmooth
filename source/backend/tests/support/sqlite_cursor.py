import support.sqlite_db as _m

class TestDatabaseCloseExecute:
    def close(self):
        for p in self._patches:
            p.stop()
        self._patches = []
        self.dir.cleanup()

    # ---- fixtures -------------------------------------------------------------------------
    def execute(self, sql, params=()):
        conn = self.connect()
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def query(self, sql, params=()):
        conn = self.connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(sql, params)
            return cur.fetchall()
        finally:
            conn.close()

    def one(self, sql, params=()):
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def add_user(self, role, name, email=None, active=1):
        email = email or f"{name.lower().replace(' ', '.')}@ku.th"
        year = 3 if role == "undergrad_student" else None
        return self.execute(
            "INSERT INTO users (full_name, email, password_hash, role, year, is_active, email_verified) "
            "VALUES (%s, %s, %s, %s, %s, %s, 1)",
            (name, email, "x", role, year, active),
        )

    def add_resource(self, name, category="Fabrication", status="Available", **extra):
        code = f"RES-{self.one('SELECT COUNT(*) AS n FROM resources')['n'] + 1:04d}"
        return self.execute(
            "INSERT INTO resources (resource_code, name, type, category, location, owner, status, is_archived) "
            "VALUES (%s, %s, 'Equipment', %s, 'Lab A', 'Admin', %s, %s)",
            (code, name, category, status, extra.get("archived", 0)),
        )

    def add_booking(self, resource_id, user_id, start, end, status="Approved", purpose="Test", **extra):
        return self.execute(
            "INSERT INTO bookings (resource_id, requester_id, start_time, end_time, purpose, status, "
            "checked_in_at, checked_out_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (resource_id, user_id, start, end, purpose, status, extra.get("checked_in_at"), extra.get("checked_out_at")),
        )
