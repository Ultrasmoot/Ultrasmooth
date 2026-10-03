# Panyasiri
import datetime

import mysql.connector

from database.db import get_connection

VALID_DECISIONS = {"approve": "Approved", "reject": "Rejected"}
REQUIRED_FIELDS = ["resource_id", "start_time", "end_time", "purpose"]
MAX_PURPOSE_LENGTH = 255  # limit bookings purpose to VARCHAR(255)

# returns the resource name and requester name/email along with booking
_SELECT_WITH_NAMES = """
    SELECT b.*,
           r.name      AS resource_name,
           u.full_name AS requester_name,
           u.email     AS requester_email
    FROM bookings b
    JOIN resources r ON r.id = b.resource_id
    JOIN users u     ON u.id = b.requester_id
"""


class ValidationError(Exception):
    pass


class BookingModel:

    @staticmethod
    def list_pending():
        # US-5: admin review queue
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                _SELECT_WITH_NAMES + " WHERE b.status = 'Pending' ORDER BY b.start_time ASC"
            )
            return cur.fetchall()
        finally:
            conn.close()

    @staticmethod
    def list_history():
        # Admin history: requests already decided
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                _SELECT_WITH_NAMES
                + " WHERE b.status <> 'Pending' ORDER BY b.decided_at DESC, b.id DESC"
            )
            return cur.fetchall()
        finally:
            conn.close()
            
    # US-5: approve/reject
    @classmethod
    def decide(cls, booking_id: int, decision: str, admin_id: int):
        if decision not in VALID_DECISIONS:
            raise ValidationError("decision must be 'approve' or 'reject'.")

        booking = cls.get(booking_id)
        if not booking:
            raise ValidationError("Booking not found.")
        if booking["status"] != "Pending":
            raise ValidationError(f"This booking was already {booking['status'].lower()}.")

        conn = get_connection()
        try:
            cur = conn.cursor()
            # prevent 2 admins overwrite each other
            cur.execute(
                """UPDATE bookings SET status=%s, decided_by=%s, decided_at=NOW()
                   WHERE id=%s AND status='Pending'""",
                (VALID_DECISIONS[decision], admin_id, booking_id),
            )
            changed = cur.rowcount
            conn.commit()
        finally:
            conn.close()

        if changed == 0:
            latest = cls.get(booking_id)
            status = latest["status"].lower() if latest else "decided"
            raise ValidationError(f"This booking was already {status}.")
        return cls.get(booking_id)