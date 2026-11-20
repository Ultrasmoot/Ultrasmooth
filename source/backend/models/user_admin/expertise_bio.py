# expertise and bio helpers for user admin
import models.user_admin.model as _m

def _expertise(value):
    """Clean and remove duplicate expertise topics."""
    if value is None:
        return ""
    if isinstance(value, list):
        value = ",".join(str(v) for v in value)
    if not isinstance(value, str):
        raise _m.ValidationError("Expertise must be text.")
    seen, tags = set(), []
    for tag in value.split(","):
        tag = " ".join(tag.split())
        if not tag or tag.lower() in seen:
            continue
        if len(tag) > _m.MAX_TAG:
            raise _m.ValidationError(f"Each expertise topic must be at most {_m.MAX_TAG} characters.")
        seen.add(tag.lower())
        tags.append(tag)
    text = ",".join(tags)
    if len(text) > _m.MAX_PROFILE_TEXT:
        raise _m.ValidationError(f"Expertise must be at most {_m.MAX_PROFILE_TEXT} characters in total.")
    return text

def _bio(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise _m.ValidationError("Bio must be text.")
    value = " ".join(value.split())
    if len(value) > _m.MAX_PROFILE_TEXT:
        raise _m.ValidationError(f"Bio must be at most {_m.MAX_PROFILE_TEXT} characters.")
    return value

def _lock_admins(cur):
    """Lock admin rows in a consistent order to prevent concurrent changes."""
    cur.execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id FOR UPDATE")
    cur.fetchall()

def _other_active_admins(cur, user_id):
    cur.execute("SELECT COUNT(*) AS n FROM users WHERE role = 'admin' AND is_active = 1 AND id <> %s", (user_id,))
    return cur.fetchone()["n"]

def serialize(row: dict) -> dict:
    """Return user data without sensitive fields."""
    return {
        "id": row["id"],
        "student_id": row["student_id"],
        "full_name": row["full_name"] or "",
        "email": row["email"],
        "role": row["role"],
        "role_label": _m.ROLE_LABEL.get(row["role"], row["role"]),
        "faculty": row["faculty"],
        "major": row["major"],
        "year": row["year"],
        "is_active": bool(row["is_active"]),
        "email_verified": bool(row["email_verified"]),
        "google_linked": bool(row["google_linked"]),
        "expertise": row["expertise"] if row["role"] == "professor" else "",
        "bio": row["bio"] if row["role"] == "professor" else "",
        "created_at": _m.iso(row["created_at"]),
    }