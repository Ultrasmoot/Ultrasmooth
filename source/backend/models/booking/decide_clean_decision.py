import models.booking.model as _m

class BookingModelDecideCleanDecision:
    # approve or rejected
    @classmethod
    def decide(cls, booking_id: int, decision: str, admin_id: int, reason=None):
        reason = cls._clean_decision(decision, reason)
        booking = cls.get(booking_id)
        if not booking:
            raise _m.ValidationError("Booking not found.")

        conn = _m.get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            # locks the resource first, then checks the latest booking status to prevent conflicts 
            # with new bookings or other admins
            resource, current = _m.lock_resource_then_booking(
                cur, booking["resource_id"], booking_id, "status, is_archived")
            if not current:
                raise _m.ValidationError("Booking not found.")
            if current["status"] != "Pending":
                raise _m.ValidationError(f"This booking was already {current['status'].lower()}.")
            if decision == "approve":
                cls._check_approvable(conn, resource, current, booking_id)
            cur.execute(
                """UPDATE bookings SET status=%s, decided_by=%s, decided_at=NOW(), decision_reason=%s
                   WHERE id=%s AND status='Pending'""",
                (_m.VALID_DECISIONS[decision], admin_id, reason, booking_id),
            )
            if cur.rowcount == 0:
                raise _m.ValidationError("This booking was already decided.")
            _m.events.booking_decided(conn, booking_id, admin_id)   # Iteration 5
            conn.commit()
        except _m.ValidationError:
            conn.rollback()
            raise
        finally:
            conn.close()
        return cls.get(booking_id)

    @staticmethod
    def _clean_decision(decision, reason):
        if not isinstance(decision, str) or decision not in _m.VALID_DECISIONS:
            raise _m.ValidationError("decision must be 'approve' or 'reject'.")
        # The reason is an optional note and only exists for a rejection for an
        # approval it is ignored. A blank reason is stored as NULL.
        if decision != "reject":
            return None
        if reason is not None and not isinstance(reason, str):
            raise _m.ValidationError("reason must be text.")
        reason = (reason or "").strip() or None
        if reason and len(reason) > _m.MAX_REASON_LENGTH:
            raise _m.ValidationError(
                f"reason must be at most {_m.MAX_REASON_LENGTH} characters (currently {len(reason)})."
            )
        return reason
