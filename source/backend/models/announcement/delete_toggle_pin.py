# delete and pin actions for announcements
import models.announcement.model as _m

class AnnouncementModelDeleteTogglePin:
    @classmethod
    def delete(cls, announcement_id: int, user_id: int):
        """Delete an announcement owned by the user."""
        announcement = cls.get(announcement_id)
        if not announcement:
            raise _m.ValidationError("Announcement not found.")
        if announcement["author_id"] != user_id:
            raise _m.ValidationError("You can only delete your own announcement.")
        conn = _m.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM announcements WHERE id = %s", (announcement_id,))
            _m.events.announcement_deleted(conn, announcement_id, announcement["title"], user_id)
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def toggle_pin(cls, announcement_id: int):
        announcement = cls.get(announcement_id)
        if not announcement:
            raise _m.ValidationError("Announcement not found.")
        conn = _m.get_connection()
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