from database.db import get_connection
from services.events import service as events  # activity log + notifications

POSTER_ROLES = {"professor", "admin"}
MAX_TITLE_LENGTH = 150
MAX_BODY_LENGTH = 10000 


class ValidationError(Exception):
    pass


from models.announcement.delete_toggle_pin import AnnouncementModelDeleteTogglePin  # noqa: E402


class AnnouncementModel(AnnouncementModelDeleteTogglePin):
    @staticmethod
    def _validate(data: dict):
        for field in ("title", "body"):
            if data.get(field) is not None and not isinstance(data.get(field), str):
                raise ValidationError(f"{field} must be text.")
        title = (data.get("title") or "").strip()
        body = (data.get("body") or "").strip()
        if not title:
            raise ValidationError("title is required.")
        if not body:
            raise ValidationError("body is required.")
        if len(title) > MAX_TITLE_LENGTH:
            raise ValidationError(f"title must be at most {MAX_TITLE_LENGTH} characters.")
        if len(body) > MAX_BODY_LENGTH:
            raise ValidationError(f"body must be at most {MAX_BODY_LENGTH} characters.")
        return title, body

    @staticmethod
    def get(announcement_id: int):
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM announcements WHERE id = %s", (announcement_id,))
            return cur.fetchone()
        finally:
            conn.close()

    @staticmethod
    def list():
        """Pinned announcements first, newest first within each group."""
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT * FROM announcements ORDER BY is_pinned DESC, created_at DESC"
            )
            return cur.fetchall()
        finally:
            conn.close()

    @classmethod
    def create(cls, data: dict, author_id: int):
        title, body = cls._validate(data)
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO announcements (author_id, title, body) VALUES (%s, %s, %s)",
                (author_id, title, body),
            )
            new_id = cur.lastrowid
            events.announcement_posted(conn, new_id, author_id) 
            conn.commit()
            return cls.get(new_id)
        finally:
            conn.close()
