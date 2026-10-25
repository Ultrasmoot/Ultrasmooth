from database.db import get_connection

POSTER_ROLES = {"professor", "admin"}


class ValidationError(Exception):
    pass


class AnnouncementModel:
    @staticmethod
    def _validate(data: dict):
        title = str(data.get("title") or "").strip()
        body = str(data.get("body") or "").strip()
        if not title:
            raise ValidationError("title is required.")
        if not body:
            raise ValidationError("body is required.")
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
    # Pinned announcements first, newest first within each group
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
            conn.commit()
            return cls.get(cur.lastrowid)
        finally:
            conn.close()

    @classmethod
    def delete(cls, announcement_id: int, user_id: int):
    # Only the author may delete their own announcement
        announcement = cls.get(announcement_id)
        if not announcement:
            raise ValidationError("Announcement not found.")
        if announcement["author_id"] != user_id:
            raise ValidationError("You can only delete your own announcement.")
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM announcements WHERE id = %s", (announcement_id,))
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def toggle_pin(cls, announcement_id: int):
        announcement = cls.get(announcement_id)
        if not announcement:
            raise ValidationError("Announcement not found.")
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE announcements SET is_pinned = %s WHERE id = %s",
                (0 if announcement["is_pinned"] else 1, announcement_id),
            )
            conn.commit()
            return cls.get(announcement_id)
        finally:
            conn.close()
