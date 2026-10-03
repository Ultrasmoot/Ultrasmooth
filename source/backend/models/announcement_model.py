from database.db import get_connection

POSTER_ROLES = {"professor", "admin"}


class ValidationError(Exception):
    pass


class AnnouncementModel:
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
