import services.events.service as _m

def appointment_cancelled(conn, appt_id, was_status="Pending"):
    a = _m._appointment(conn, appt_id)
    if not a:
        return
    accepted = was_status == "Accepted"
    _m.log(conn, a["student_id"], "appointment.cancelled",
        f"{a['professor_name']} - {a['topic']} ({_m._when(a['start_time'], a['end_time'])})"
        + (" (was accepted)" if accepted else ""), None, "appointment", appt_id)
    _m.notify(conn, [a["professor_id"]], "appointment.cancelled",
           "Appointment cancelled" if accepted else "Appointment request cancelled",
           f"{a['student_name']} cancelled: {a['topic']}" + (f", {_m._when(a['start_time'], a['end_time'])}" if accepted else ""),
           "appointments")

# ---------------------- user management ----------------------
def user_event(conn, admin_id, action, target_id, summary):
    """One activity-log row for an account change made by an administrator."""
    _m.log(conn, admin_id, action, summary, None, "user", target_id)
