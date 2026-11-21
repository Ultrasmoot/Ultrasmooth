# user update logging and validation helpers
import models.user_admin.model as _m

class UserAdminModelLogUpdateIso:
    @staticmethod
    def _log_update(conn, admin_id, user_id, before_after, role_changed, changed, unlink_google):
        old, f = before_after
        who = f"{f['full_name']} ({f['email']})"
        if role_changed:
            _m.events.user_event(conn, admin_id, "user.role_changed", user_id,
                                 f"{who}: {_m.ROLE_LABEL[old['role']]} -> {_m.ROLE_LABEL[f['role']]}")
        if changed:
            note = " (Google link removed)" if unlink_google else ""
            _m.events.user_event(conn, admin_id, "user.updated", user_id,
                                 f"{who}: changed {', '.join(changed)}{note}")

def iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value

def _email(value):
    value = value.strip().lower() if isinstance(value, str) else ""
    if not value:
        raise _m.ValidationError("Email is required.")
    if len(value) > _m.MAX_TEXT_LENGTH or not _m._EMAIL.match(value):
        raise _m.ValidationError("Please enter a valid email address.")
    return value

def _role(value):
    if not isinstance(value, str) or value.strip() not in _m.ALL_ROLES:
        raise _m.ValidationError("Please choose a role.")
    return value.strip()

def _student_id(value):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str) or not _m._STUDENT_ID.fullmatch(value.strip()):
        raise _m.ValidationError("Student ID must be exactly 10 digits.")
    return value.strip()