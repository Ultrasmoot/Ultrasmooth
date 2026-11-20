import datetime
import models.appointment.model as _m

def _now():
    return datetime.datetime.now()

def _text(value, name, minimum=0, maximum=500, required=False):
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise _m.ValidationError(f"{name} is required.")
        return None
    if not isinstance(value, str):
        raise _m.ValidationError(f"{name} must be text.")
    value = " ".join(value.split())
    if len(value) < minimum:
        raise _m.ValidationError(f"{name} must be at least {minimum} characters.")
    if len(value) > maximum:
        raise _m.ValidationError(f"{name} must be at most {maximum} characters.")
    return value

def _parse_start(value, now):
    if not isinstance(value, str) or not value.strip():
        raise _m.ValidationError("A date and time is required.")
    try:
        start = datetime.datetime.fromisoformat(value.strip())
    except ValueError:
        raise _m.ValidationError("The date and time is not valid.")
    if start.tzinfo is not None:
        start = start.astimezone().replace(tzinfo=None)
    start = start.replace(second=0, microsecond=0)
    if start <= now:
        raise _m.ValidationError("The appointment must be in the future.")
    if start > now + datetime.timedelta(days=_m.MAX_DAYS_AHEAD):
        raise _m.ValidationError(f"The appointment must be within {_m.MAX_DAYS_AHEAD} days.")
    return start

class AppointmentModelNowText:
    # ---------- the directory students choose from ----------
    @staticmethod
    def professors():
        conn = _m.get_connection()
        try:
            cur = conn.cursor(dictionary=True, buffered=True)
            cur.execute(
                """SELECT u.id, u.full_name, COALESCE(p.expertise, '') AS expertise,
                          COALESCE(p.bio, '') AS bio, p.photo_path
                   FROM users u LEFT JOIN professor_profiles p ON p.user_id = u.id
                   WHERE u.role = 'professor' AND u.is_active = 1 ORDER BY u.full_name"""
            )
            return cur.fetchall()
        finally:
            conn.close()
