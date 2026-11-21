import datetime
import services.events.service as _m

def _now():
    return datetime.datetime.now()

def _cur(conn):
    return conn.cursor(dictionary=True, buffered=True)

def _clip(text, limit):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"

def _when(start, end=None):
    """'12 Oct 10:00-12:00' (or both dates when the range crosses midnight)."""
    if not isinstance(start, datetime.datetime):
        return ""
    text = f"{start:%d %b %H:%M}"
    if isinstance(end, datetime.datetime):
        text += f"-{end:%H:%M}" if end.date() == start.date() else f" - {end:%d %b %H:%M}"
    return text

#  ---------------------- low level ----------------------
def log(conn, actor_id, action, summary, resource_id=None, target_type=None, target_id=None, actor_name=None):
    """Append one row to activity_log inside the caller's transaction."""
    if action not in _m.ACTIONS:
        raise ValueError(f"unknown activity action: {action}")
    cur = _m._cur(conn)
    summary = _m._clip(summary, _m.SUMMARY_MAX)
    if actor_id is not None:
        # The name is copied from users in the same statement (a snapshot).
        cur.execute(
            """INSERT INTO activity_log
                   (actor_id, actor_name, action, resource_id, target_type, target_id, summary, created_at)
               SELECT id, COALESCE(NULLIF(full_name, ''), email), %s, %s, %s, %s, %s, %s
               FROM users WHERE id = %s""",
            (action, resource_id, target_type, target_id, summary, _m._now(), actor_id),
        )
        if cur.rowcount:
            return
    cur.execute(
        """INSERT INTO activity_log
               (actor_id, actor_name, action, resource_id, target_type, target_id, summary, created_at)
           VALUES (NULL, %s, %s, %s, %s, %s, %s, %s)""",
        (_m._clip(actor_name or "System", 150), action, resource_id, target_type, target_id, summary, _m._now()),
    )

def notify(conn, user_ids, kind, title, body, link_view, exclude_id=None):
    """One notification per recipient (duplicates and the acting user are skipped)."""
    ids = sorted({int(u) for u in user_ids if u is not None and u != exclude_id})
    if not ids:
        return
    now = _m._now()
    _m._cur(conn).executemany(
        """INSERT INTO notifications (user_id, kind, title, body, link_view, created_at)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        [(uid, kind, _m._clip(title, _m.TITLE_MAX), _m._clip(body, _m.BODY_MAX), link_view, now) for uid in ids],
    )

def _user_ids(conn, roles=None):
    cur = _m._cur(conn)
    if roles:
        marks = ", ".join(["%s"] * len(roles))
        cur.execute(f"SELECT id FROM users WHERE is_active = 1 AND role IN ({marks})", tuple(roles))
    else:
        cur.execute("SELECT id FROM users WHERE is_active = 1")
    return [r["id"] for r in cur.fetchall()]
