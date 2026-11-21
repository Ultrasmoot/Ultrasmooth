import datetime
import logging
import threading
import time

from config import Config
from database.db import get_connection
from services.events import service as events
from services.locking.service import lock_resource_then_booking 

logger = logging.getLogger(__name__)

DELETE_BATCH = 1000
PURGE_EVERY_SECONDS = 3600


from services.housekeeping.now_overdue_ids import _now, _overdue_ids, _close_one 
from services.housekeeping.start_background_worker import start_background_worker 


def auto_checkout_overdue(now=None, grace_minutes=None):
    # returns how many bookings were checked out. One failing booking never stops the others
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


def _purge(table, column, cutoff):
    # deletes rows older than `cutoff` in small batches so no long lock is held
    total = 0
    while True:
        conn = get_connection()
        try:
            cur = conn.cursor()
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
    # returns (notifications_deleted, activity_rows_deleted). 0 days = keep forever
    now = now or _now()
    n_days = Config.NOTIFICATION_RETENTION_DAYS if notification_days is None else notification_days
    a_days = Config.ACTIVITY_RETENTION_DAYS if activity_days is None else activity_days
    notifications = activity = 0
    if n_days > 0:
        notifications = _purge("notifications", "created_at", now - datetime.timedelta(days=n_days))
    if a_days > 0:
        activity = _purge("activity_log", "created_at", now - datetime.timedelta(days=a_days))
    return notifications, activity


def run_once(purge=False):
    closed = auto_checkout_overdue()
    deleted = purge_old_records() if purge else (0, 0)
    return closed, deleted
