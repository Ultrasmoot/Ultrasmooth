# in-web notifications (the bell). Creating them is done by services/events.py.
from database.db import get_connection

LIST_LIMIT = 30


class NotificationModel:

    @staticmethod
    def list(user_id: int, limit: int = LIST_LIMIT):
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT * FROM notifications WHERE user_id = %s ORDER BY created_at DESC, id DESC LIMIT %s",
                (user_id, limit),
            )
            return cur.fetchall()
        finally:
            conn.close()

    @staticmethod
    def unread_count(user_id: int) -> int:
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT COUNT(*) AS n FROM notifications WHERE user_id = %s AND is_read = 0", (user_id,))
            return cur.fetchone()["n"]
        finally:
            conn.close()

    @staticmethod
    def mark_read(user_id: int, notification_id: int) -> bool:
    # the owner can mark a notification (someone else's id simply does nothing)
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT id FROM notifications WHERE id = %s AND user_id = %s", (notification_id, user_id))
            if not cur.fetchone():
                return False
            cur.execute("UPDATE notifications SET is_read = 1 WHERE id = %s AND user_id = %s",
                        (notification_id, user_id))
            conn.commit()
            return True
        finally:
            conn.close()

    @staticmethod
    def mark_all_read(user_id: int) -> None:
        conn = get_connection()
        try:
            conn.cursor().execute("UPDATE notifications SET is_read = 1 WHERE user_id = %s AND is_read = 0", (user_id,))
            conn.commit()
        finally:
            conn.close()
