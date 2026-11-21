import datetime
import re


from services.events.now_cur import _now, _cur, _clip, _when, log, notify, _user_ids  # noqa: E402
from services.events.one_booking import _one, _booking, _issue, _people_booked_on, booking_submitted, booking_decided, booking_cancelled, checkin_done, checkin_code_failed, checkout_done  # noqa: E402
from services.events.checkout_auto_maintenance_reported import checkout_auto, maintenance_reported, _tell_bookers, maintenance_confirmed, maintenance_dismissed, maintenance_updated, maintenance_resolved, maintenance_released, resource_changed  # noqa: E402
from services.events.appointment_cancelled_user_event import appointment_cancelled, user_event  # noqa: E402

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

# Frontend view names a notification can open (the nav keys).
SUMMARY_MAX = 500
BODY_MAX = 500
TITLE_MAX = 150


_SAFE_LOGIN_CHARS = re.compile(r"[^A-Za-z0-9@._+\-]")
LOGIN_LOG_MAX = 100         
LOGIN_LOG_PER_IP = 20       
LOGIN_LOG_WINDOW = 600      


def announcement_posted(conn, announcement_id, author_id):
    a = _one(conn, "SELECT title FROM announcements WHERE id = %s", (announcement_id,))
    if not a:
        return
    log(conn, author_id, "announcement.posted", a["title"], None, "announcement", announcement_id)
    notify(conn, _user_ids(conn), "announcement.posted", "New announcement", a["title"], "home",
           exclude_id=author_id)


def announcement_deleted(conn, announcement_id, title, user_id):
    log(conn, user_id, "announcement.deleted", title, None, "announcement", announcement_id)


def _safe_login_name(email):
    """The e-mail typed on the login form comes from someone who is not signed in, so it is reduced to
    plain address characters before it is stored (no markup, no line breaks, no look-alike text)."""
    return _SAFE_LOGIN_CHARS.sub("?", str(email or "").strip())[:LOGIN_LOG_MAX] or "(empty)"


def login_failed(email, ip=None):
    """No signed-in user and no surrounding transaction, so this uses its own connection.
    Never raises: a failure to write the log must not change the login response.
    The text is sanitised, and one address can only add LOGIN_LOG_PER_IP rows per window, so the
    log cannot be flooded or filled with attacker-written text by anonymous requests."""
    try:
        if ip:
            from middleware.rate_limit import check_rate_limit
            allowed, _ = check_rate_limit(f"loginlog:{ip}", LOGIN_LOG_PER_IP, LOGIN_LOG_WINDOW)
            if not allowed:
                return
        from database.db import get_connection
        name = _safe_login_name(email)
        conn = get_connection()
        try:
            log(conn, None, "auth.login_failed", f"Failed login for {name}", actor_name=name)
            conn.commit()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 - see docstring
        pass


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
