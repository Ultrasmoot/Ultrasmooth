import datetime
import logging
import threading
import time

from config import Config
from database.db import get_connection
from services import events

logger = logging.getLogger(__name__)

DELETE_BATCH = 1000
PURGE_EVERY_SECONDS = 3600


def _now():
    return datetime.datetime.now()


# auto check-out
def _overdue_ids(now, grace_minutes):
    cutoff = now - datetime.timedelta(minutes=grace_minutes)
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """SELECT id FROM bookings
               WHERE status = 'Approved' AND checked_in_at IS NOT NULL
                 AND checked_out_at IS NULL AND end_time <= %s ORDER BY id""",
            (cutoff,),
        )
        return [r["id"] for r in cur.fetchall()]
    finally:
        conn.close()


def _close_one(booking_id, now, grace_minutes):
    # Checks one overdue booking out. Returns True if this call did it
    cutoff = now - datetime.timedelta(minutes=grace_minutes)
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT resource_id FROM bookings WHERE id = %s", (booking_id,))
        row = cur.fetchone()
        if not row:
            return False
        resource_id = row["resource_id"]
        cur.execute("SELECT id, status FROM resources WHERE id = %s FOR UPDATE", (resource_id,))
        resource = cur.fetchone()
        cur.execute("SELECT * FROM bookings WHERE id = %s FOR UPDATE", (booking_id,))
        booking = cur.fetchone()
        # Re-check under the lock: the user may have checked out a moment ago.
        if (not booking or booking["status"] != "Approved" or not booking["checked_in_at"]
                or booking["checked_out_at"] or booking["end_time"] > cutoff):
            conn.rollback()
            return False
        cur.execute("UPDATE bookings SET checked_out_at = %s WHERE id = %s AND checked_out_at IS NULL",
                    (now, booking_id))
        if cur.rowcount == 0:
            conn.rollback()
            return False
        # Free the resource only if it is still "In Use" and nobody else is checked in.
        # (If it went into Maintenance meanwhile it stays blocked.)
        if resource and resource["status"] == "In Use":
            cur.execute(
                """SELECT COUNT(*) AS n FROM bookings
                   WHERE resource_id = %s AND id <> %s AND status = 'Approved'
                     AND checked_in_at IS NOT NULL AND checked_out_at IS NULL""",
                (resource_id, booking_id),
            )
            if cur.fetchone()["n"] == 0:
                cur.execute("UPDATE resources SET status = 'Available' WHERE id = %s", (resource_id,))
        events.checkout_auto(conn, booking_id)
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def auto_checkout_overdue(now=None, grace_minutes=None):
    # Returns how many bookings were checked out. One failing booking never stops the others
    now = now or _now()
    grace = Config.AUTO_CHECKOUT_GRACE_MINUTES if grace_minutes is None else grace_minutes
    closed = 0
    for booking_id in _overdue_ids(now, grace):
        try:
            if _close_one(booking_id, now, grace):
                closed += 1
        except Exception:
            logger.exception("Auto check-out failed for booking %s", booking_id)
    return closed


# retention
def _purge(table, column, cutoff):
    # Deletes rows older than `cutoff` in small batches so no long lock is held
    total = 0
    while True:
        conn = get_connection()
        try:
            cur = conn.cursor()
            # The derived table keeps this valid on MySQL (no LIMIT inside IN) and SQLite (tests)
            cur.execute(
                f"DELETE FROM {table} WHERE id IN "
                f"(SELECT id FROM (SELECT id FROM {table} WHERE {column} < %s LIMIT {DELETE_BATCH}) AS old_rows)",
                (cutoff,),
            )
            n = cur.rowcount
            conn.commit()
        finally:
            conn.close()
        total += n
        if n < DELETE_BATCH:
            return total


def purge_old_records(now=None, notification_days=None, activity_days=None):
    # Returns (notifications_deleted, activity_rows_deleted). 0 days = keep forever
    now = now or _now()
    n_days = Config.NOTIFICATION_RETENTION_DAYS if notification_days is None else notification_days
    a_days = Config.ACTIVITY_RETENTION_DAYS if activity_days is None else activity_days
    notifications = activity = 0
    if n_days > 0:
        notifications = _purge("notifications", "created_at", now - datetime.timedelta(days=n_days))
    if a_days > 0:
        activity = _purge("activity_log", "created_at", now - datetime.timedelta(days=a_days))
    return notifications, activity


# worker
def run_once(purge=False):
    closed = auto_checkout_overdue()
    deleted = purge_old_records() if purge else (0, 0)
    return closed, deleted


def start_background_worker():
    # Starts one daemon thread: auto check-out every JOB_INTERVAL_SECONDS, retention hourly.
    # Errors are logged and never stop the loop.

    def _loop():
        last_purge = 0.0
        while True:
            try:
                due = time.monotonic() - last_purge >= PURGE_EVERY_SECONDS
                closed, deleted = run_once(purge=due)
                if due:
                    last_purge = time.monotonic()
                if closed or any(deleted):
                    logger.info("housekeeping: %s auto check-out(s), deleted %s notification(s) and %s log row(s)",
                                closed, deleted[0], deleted[1])
            except Exception:
                logger.exception("housekeeping run failed")
            time.sleep(Config.JOB_INTERVAL_SECONDS)

    thread = threading.Thread(target=_loop, name="vase-housekeeping", daemon=True)
    thread.start()
    return thread
