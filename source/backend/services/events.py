import datetime

ACTIONS = {
    "booking.submitted": "Booking submitted",
    "booking.approved": "Booking approved",
    "booking.rejected": "Booking rejected",
    "checkin.done": "Check-in",
    "checkin.code_failed": "Check-in code failed",
    "checkout.done": "Check-out",
    "checkout.auto": "Automatic check-out",
    "booking.cancelled": "Booking cancelled",
    "maintenance.reported": "Issue reported",
    "maintenance.confirmed": "Issue confirmed",
    "maintenance.dismissed": "Issue dismissed",
    "maintenance.updated": "Issue updated",
    "maintenance.resolved": "Issue resolved",
    "maintenance.released": "Resource restored",
    "resource.created": "Resource created",
    "resource.updated": "Resource edited",
    "resource.archived": "Resource archived",
    "resource.unarchived": "Resource restored from archive",
    "announcement.posted": "Announcement posted",
    "announcement.deleted": "Announcement deleted",
    "auth.login_failed": "Login failed",
    "appointment.requested": "Appointment requested",
    "appointment.accepted": "Appointment accepted",
    "appointment.declined": "Appointment declined",
    "appointment.cancelled": "Appointment cancelled",
    "user.created": "User created",
    "user.updated": "User edited",
    "user.role_changed": "Role changed",
    "user.deactivated": "User deactivated",
    "user.reactivated": "User reactivated",
}

# max length of text columns
SUMMARY_MAX = 500
BODY_MAX = 500
TITLE_MAX = 150


def _now():
    return datetime.datetime.now()


def _cur(conn):
    return conn.cursor(dictionary=True, buffered=True)


def _clip(text, limit):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _when(start, end=None):
    # Includes the end date if the range crosses midnight
    if not isinstance(start, datetime.datetime):
        return ""
    text = f"{start:%d %b %H:%M}"
    if isinstance(end, datetime.datetime):
        text += f"-{end:%H:%M}" if end.date() == start.date() else f" - {end:%d %b %H:%M}"
    return text


# core 
def log(conn, actor_id, action, summary, resource_id=None, target_type=None, target_id=None, actor_name=None):
    """Add a row to activity_log. Doesn't commit, the caller does that."""
    if action not in ACTIONS:
        raise ValueError(f"unknown activity action: {action}")
    cur = _cur(conn)
    summary = _clip(summary, SUMMARY_MAX)
    if actor_id is not None:
        # Keep the name as it was when the log was created
        cur.execute(
            """INSERT INTO activity_log
                   (actor_id, actor_name, action, resource_id, target_type, target_id, summary, created_at)
               SELECT id, COALESCE(NULLIF(full_name, ''), email), %s, %s, %s, %s, %s, %s
               FROM users WHERE id = %s""",
            (action, resource_id, target_type, target_id, summary, _now(), actor_id),
        )
        if cur.rowcount:
            return
    cur.execute(
        """INSERT INTO activity_log
               (actor_id, actor_name, action, resource_id, target_type, target_id, summary, created_at)
           VALUES (NULL, %s, %s, %s, %s, %s, %s, %s)""",
        (_clip(actor_name or "System", 150), action, resource_id, target_type, target_id, summary, _now()),
    )


def notify(conn, user_ids, kind, title, body, link_view, exclude_id=None):
    """Send a notification to each user. link_view is the frontend nav key.
    exclude_id is usually the person who did the action (no need to notify yourself)."""
    ids = sorted({int(u) for u in user_ids if u is not None and u != exclude_id})
    if not ids:
        return
    now = _now()
    _cur(conn).executemany(
        """INSERT INTO notifications (user_id, kind, title, body, link_view, created_at)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        [(uid, kind, _clip(title, TITLE_MAX), _clip(body, BODY_MAX), link_view, now) for uid in ids],
    )


def _user_ids(conn, roles=None):
    cur = _cur(conn)
    if roles:
        marks = ", ".join(["%s"] * len(roles))
        cur.execute(f"SELECT id FROM users WHERE is_active = 1 AND role IN ({marks})", tuple(roles))
    else:
        cur.execute("SELECT id FROM users WHERE is_active = 1")
    return [r["id"] for r in cur.fetchall()]


def _one(conn, sql, params):
    cur = _cur(conn)
    cur.execute(sql, params)
    return cur.fetchone()


def _booking(conn, booking_id):
    return _one(
        conn,
        """SELECT b.*, r.name AS resource_name, u.full_name AS requester_name
           FROM bookings b JOIN resources r ON r.id = b.resource_id
           JOIN users u ON u.id = b.requester_id WHERE b.id = %s""",
        (booking_id,),
    )


def _issue(conn, record_id):
    return _one(
        conn,
        """SELECT m.*, r.name AS resource_name FROM maintenance_records m
           JOIN resources r ON r.id = m.resource_id WHERE m.id = %s""",
        (record_id,),
    )


def _people_booked_on(conn, resource_id):
    # Users with an active pending or approved booking for this resource
    cur = _cur(conn)
    cur.execute(
        """SELECT DISTINCT requester_id FROM bookings
           WHERE resource_id = %s AND status IN ('Pending', 'Approved')
             AND end_time > %s AND checked_out_at IS NULL""",
        (resource_id, _now()),
    )
    return [r["requester_id"] for r in cur.fetchall()]


# bookings
def booking_submitted(conn, booking_id):
    b = _booking(conn, booking_id)
    if not b:
        return
    what = f"{b['resource_name']}, {_when(b['start_time'], b['end_time'])}"
    log(conn, b["requester_id"], "booking.submitted", f"{what} - {b['purpose']}",
        b["resource_id"], "booking", booking_id)
    notify(conn, _user_ids(conn, ["admin"]), "booking.submitted", "New booking request",
           f"{b['requester_name']} requested {what}", "bookings", exclude_id=b["requester_id"])


def booking_decided(conn, booking_id, admin_id):
    b = _booking(conn, booking_id)
    if not b or b["status"] not in ("Approved", "Rejected"):
        return
    approved = b["status"] == "Approved"
    what = f"{b['resource_name']}, {_when(b['start_time'], b['end_time'])}"
    reason = b.get("decision_reason")
    log(conn, admin_id, "booking.approved" if approved else "booking.rejected",
        f"{what} for {b['requester_name']}" + (f' - "{reason}"' if reason else ""),
        b["resource_id"], "booking", booking_id)
    notify(conn, [b["requester_id"]], "booking.decided",
           "Booking approved" if approved else "Booking declined",
           what + (f' - "{reason}"' if reason else ""), "bookings", exclude_id=admin_id)


def booking_cancelled(conn, booking_id, was_status):
    # Log when a requester cancels a pending or approved booking they haven't used
    b = _booking(conn, booking_id)
    if not b:
        return
    what = f"{b['resource_name']}, {_when(b['start_time'], b['end_time'])}"
    log(conn, b["requester_id"], "booking.cancelled", f"{what} (was {was_status})",
        b["resource_id"], "booking", booking_id)
    if was_status == "Approved":
        # Notify admins because the cancelled slot is available again
        notify(conn, _user_ids(conn, ["admin"]), "booking.cancelled", "Booking cancelled",
               f"{b['requester_name']} cancelled {what}", "bookings", exclude_id=b["requester_id"])


def checkin_done(conn, booking_id):
    b = _booking(conn, booking_id)
    if b:
        log(conn, b["requester_id"], "checkin.done", b["resource_name"], b["resource_id"], "booking", booking_id)


def checkin_code_failed(conn, booking_id, attempts_left):
    b = _booking(conn, booking_id)
    if b:
        log(conn, b["requester_id"], "checkin.code_failed",
            f"{b['resource_name']} ({attempts_left} attempt{'s' if attempts_left != 1 else ''} left)",
            b["resource_id"], "booking", booking_id)


def checkout_done(conn, booking_id):
    b = _booking(conn, booking_id)
    if b:
        log(conn, b["requester_id"], "checkout.done", b["resource_name"], b["resource_id"], "booking", booking_id)


def checkout_auto(conn, booking_id):
    # Check out the user automatically when the booking ends without a check-out
    b = _booking(conn, booking_id)
    if not b:
        return
    log(conn, b["requester_id"], "checkout.auto",
        f"{b['resource_name']} (booking ended {_when(b['end_time'])} without check-out)",
        b["resource_id"], "booking", booking_id)
    notify(conn, [b["requester_id"]], "checkout.auto", "You were checked out automatically",
           f"{b['resource_name']}: your booking ended at {b['end_time']:%H:%M}, so it was checked out for you.",
           "checkin")


# maintenance
def maintenance_reported(conn, record_id):
    m = _issue(conn, record_id)
    if not m:
        return
    confirmed = m["status"] != "Reported"
    log(conn, m["reported_by"], "maintenance.reported",
        f"{m['resource_name']}: {m['description']}" + (" (confirmed)" if confirmed else ""),
        m["resource_id"], "maintenance", record_id)
    if confirmed:   # Admin reports are already confirmed
        _tell_bookers(conn, m, m["reported_by"])
    else:
        reporter = _one(conn, "SELECT full_name FROM users WHERE id = %s", (m["reported_by"],))
        notify(conn, _user_ids(conn, ["admin"]), "maintenance.reported", "New issue report",
               f"{(reporter or {}).get('full_name') or 'Someone'} reported {m['resource_name']}: {m['description']}",
               "maintenance", exclude_id=m["reported_by"])


def _tell_bookers(conn, m, actor_id):
    notify(conn, _people_booked_on(conn, m["resource_id"]), "maintenance.affects_booking",
           "A resource you booked is under maintenance",
           f"{m['resource_name']} is now in Maintenance. Check your booking.", "bookings",
           exclude_id=actor_id)


def maintenance_confirmed(conn, record_id, admin_id):
    m = _issue(conn, record_id)
    if not m:
        return
    log(conn, admin_id, "maintenance.confirmed", f"{m['resource_name']}: {m['description']}",
        m["resource_id"], "maintenance", record_id)
    notify(conn, [m["reported_by"]], "maintenance.status", "Issue confirmed",
           f"Your report on {m['resource_name']} was confirmed.", "maintenance", exclude_id=admin_id)
    _tell_bookers(conn, m, admin_id)


def maintenance_dismissed(conn, record_id, admin_id):
    m = _issue(conn, record_id)
    if not m:
        return
    reason = m.get("dismiss_reason")
    log(conn, admin_id, "maintenance.dismissed",
        f"{m['resource_name']}: {m['description']}" + (f' - "{reason}"' if reason else ""),
        m["resource_id"], "maintenance", record_id)
    notify(conn, [m["reported_by"]], "maintenance.status", "Issue report dismissed",
           f"{m['resource_name']}" + (f': "{reason}"' if reason else ""), "maintenance", exclude_id=admin_id)


def maintenance_updated(conn, record_id, admin_id):
    m = _issue(conn, record_id)
    if m:
        log(conn, admin_id, "maintenance.updated", f"{m['resource_name']}: {m['description']} ({m['status']})",
            m["resource_id"], "maintenance", record_id)


def maintenance_resolved(conn, record_id, admin_id):
    m = _issue(conn, record_id)
    if not m:
        return
    log(conn, admin_id, "maintenance.resolved", f"{m['resource_name']}: {m['description']}",
        m["resource_id"], "maintenance", record_id)
    notify(conn, [m["reported_by"]], "maintenance.status", "Issue resolved",
           f"{m['resource_name']}: {m['description']}", "maintenance", exclude_id=admin_id)


def maintenance_released(conn, resource_id, admin_id, closed):
    r = _one(conn, "SELECT name FROM resources WHERE id = %s", (resource_id,))
    log(conn, admin_id, "maintenance.released",
        f"{(r or {}).get('name', 'Resource')} returned to Available ({closed} open issue{'s' if closed != 1 else ''} closed)",
        resource_id, "resource", resource_id)


# resources, announcements, auth 
def resource_changed(conn, action, resource_id, actor_id):
    # action = resource.created, updated, archived, unarchived
    r = _one(conn, "SELECT name, resource_code FROM resources WHERE id = %s", (resource_id,))
    if r:
        log(conn, actor_id, action, f"{r['name']} ({r['resource_code']})", resource_id, "resource", resource_id)


def announcement_posted(conn, announcement_id, author_id):
    a = _one(conn, "SELECT title FROM announcements WHERE id = %s", (announcement_id,))
    if not a:
        return
    log(conn, author_id, "announcement.posted", a["title"], None, "announcement", announcement_id)
    notify(conn, _user_ids(conn), "announcement.posted", "New announcement", a["title"], "home",
           exclude_id=author_id)


def announcement_deleted(conn, announcement_id, title, user_id):
    log(conn, user_id, "announcement.deleted", title, None, "announcement", announcement_id)


def login_failed(email):
    # Log failures separately without affecting the login response
    from database.db import get_connection
    try:
        conn = get_connection()
        try:
            log(conn, None, "auth.login_failed", f"Failed login for {_clip(email, 150)}", actor_name=_clip(email, 150))
            conn.commit()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        pass


# appointments
def _appointment(conn, appt_id):
    return _one(
        conn,
        """SELECT a.*, s.full_name AS student_name, p.full_name AS professor_name
           FROM appointments a JOIN users s ON s.id = a.student_id JOIN users p ON p.id = a.professor_id
           WHERE a.id = %s""",
        (appt_id,),
    )


def appointment_requested(conn, appt_id):
    a = _appointment(conn, appt_id)
    if not a:
        return
    log(conn, a["student_id"], "appointment.requested",
        f"{a['professor_name']} - {a['topic']} ({_when(a['start_time'], a['end_time'])})", None, "appointment", appt_id)
    notify(conn, [a["professor_id"]], "appointment.requested", "New appointment request",
           f"{a['student_name']} - {a['topic']}, {_when(a['start_time'], a['end_time'])}", "appointments")


def appointment_decided(conn, appt_id, professor_id):
    a = _appointment(conn, appt_id)
    if not a or a["status"] not in ("Accepted", "Declined"):
        return
    accepted = a["status"] == "Accepted"
    reason = a.get("decision_reason")
    log(conn, professor_id, "appointment.accepted" if accepted else "appointment.declined",
        f"{a['student_name']} - {a['topic']} ({_when(a['start_time'], a['end_time'])})"
        + (f' - "{reason}"' if reason else ""), None, "appointment", appt_id)
    notify(conn, [a["student_id"]], "appointment.decided",
           "Appointment accepted" if accepted else "Appointment declined",
           f"{a['professor_name']}, {_when(a['start_time'], a['end_time'])}" + (f': "{reason}"' if reason else ""),
           "appointments")


def appointment_cancelled(conn, appt_id, was_status="Pending"):
    a = _appointment(conn, appt_id)
    if not a:
        return
    accepted = was_status == "Accepted"
    log(conn, a["student_id"], "appointment.cancelled",
        f"{a['professor_name']} - {a['topic']} ({_when(a['start_time'], a['end_time'])})"
        + (" (was accepted)" if accepted else ""), None, "appointment", appt_id)
    notify(conn, [a["professor_id"]], "appointment.cancelled",
           "Appointment cancelled" if accepted else "Appointment request cancelled",
           f"{a['student_name']} cancelled: {a['topic']}" + (f", {_when(a['start_time'], a['end_time'])}" if accepted else ""),
           "appointments")


# user management (US-13) 
def user_event(conn, admin_id, action, target_id, summary):
    # log when an admin changes a user account
    log(conn, admin_id, action, summary, None, "user", target_id)