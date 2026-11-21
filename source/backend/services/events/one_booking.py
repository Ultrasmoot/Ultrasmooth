import services.events.service as _m

def _one(conn, sql, params):
    cur = _m._cur(conn)
    cur.execute(sql, params)
    return cur.fetchone()

def _booking(conn, booking_id):
    return _m._one(
        conn,
        """SELECT b.*, r.name AS resource_name, u.full_name AS requester_name
           FROM bookings b JOIN resources r ON r.id = b.resource_id
           JOIN users u ON u.id = b.requester_id WHERE b.id = %s""",
        (booking_id,),
    )

def _issue(conn, record_id):
    return _m._one(
        conn,
        """SELECT m.*, r.name AS resource_name FROM maintenance_records m
           JOIN resources r ON r.id = m.resource_id WHERE m.id = %s""",
        (record_id,),
    )

def _people_booked_on(conn, resource_id):
    """Users with a pending/approved booking on this resource that has not ended yet."""
    cur = _m._cur(conn)
    cur.execute(
        """SELECT DISTINCT requester_id FROM bookings
           WHERE resource_id = %s AND status IN ('Pending', 'Approved')
             AND end_time > %s AND checked_out_at IS NULL""",
        (resource_id, _m._now()),
    )
    return [r["requester_id"] for r in cur.fetchall()]

# ---------------------- bookings ----------------------
def booking_submitted(conn, booking_id):
    b = _m._booking(conn, booking_id)
    if not b:
        return
    what = f"{b['resource_name']}, {_m._when(b['start_time'], b['end_time'])}"
    _m.log(conn, b["requester_id"], "booking.submitted", f"{what} - {b['purpose']}",
        b["resource_id"], "booking", booking_id)
    _m.notify(conn, _m._user_ids(conn, ["admin"]), "booking.submitted", "New booking request",
           f"{b['requester_name']} requested {what}", "bookings", exclude_id=b["requester_id"])

def booking_decided(conn, booking_id, admin_id):
    b = _m._booking(conn, booking_id)
    if not b or b["status"] not in ("Approved", "Rejected"):
        return
    approved = b["status"] == "Approved"
    what = f"{b['resource_name']}, {_m._when(b['start_time'], b['end_time'])}"
    reason = b.get("decision_reason")
    _m.log(conn, admin_id, "booking.approved" if approved else "booking.rejected",
        f"{what} for {b['requester_name']}" + (f' - "{reason}"' if reason else ""),
        b["resource_id"], "booking", booking_id)
    _m.notify(conn, [b["requester_id"]], "booking.decided",
           "Booking approved" if approved else "Booking declined",
           what + (f' - "{reason}"' if reason else ""), "bookings", exclude_id=admin_id)

def booking_cancelled(conn, booking_id, was_status):
    """The requester withdrew a Pending request or an Approved booking they had not used."""
    b = _m._booking(conn, booking_id)
    if not b:
        return
    what = f"{b['resource_name']}, {_m._when(b['start_time'], b['end_time'])}"
    _m.log(conn, b["requester_id"], "booking.cancelled", f"{what} (was {was_status})",
        b["resource_id"], "booking", booking_id)
    if was_status == "Approved":
        _m.notify(conn, _m._user_ids(conn, ["admin"]), "booking.cancelled", "Booking cancelled",
               f"{b['requester_name']} cancelled {what}", "bookings", exclude_id=b["requester_id"])

def checkin_done(conn, booking_id):
    b = _m._booking(conn, booking_id)
    if b:
        _m.log(conn, b["requester_id"], "checkin.done", b["resource_name"], b["resource_id"], "booking", booking_id)

def checkin_code_failed(conn, booking_id, attempts_left):
    b = _m._booking(conn, booking_id)
    if b:
        _m.log(conn, b["requester_id"], "checkin.code_failed",
            f"{b['resource_name']} ({attempts_left} attempt{'s' if attempts_left != 1 else ''} left)",
            b["resource_id"], "booking", booking_id)

def checkout_done(conn, booking_id):
    b = _m._booking(conn, booking_id)
    if b:
        _m.log(conn, b["requester_id"], "checkout.done", b["resource_name"], b["resource_id"], "booking", booking_id)
