from database.db import get_connection

POSTER_ROLES = {"professor", "admin"}


class ValidationError(Exception):
    pass


class AnnouncementModel:
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
