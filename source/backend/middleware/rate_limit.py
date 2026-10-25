import threading
import time
from collections import defaultdict, deque
from functools import wraps

from flask import jsonify, request

_lock = threading.Lock()
_hits = defaultdict(deque)  # key -> timestamps of recent attempts
_last_sweep = 0.0


def _sweep(now: float, max_window: float):
    """Drop stale keys occasionally so memory can't grow without bound."""
    global _last_sweep
    if now - _last_sweep < 60:
        return
    _last_sweep = now
    for k in [k for k, q in _hits.items() if not q or now - q[-1] > max_window]:
        del _hits[k]


def check_rate_limit(key: str, limit: int, window_seconds: int):
    """Record one attempt for `key`. Returns (allowed, retry_after_seconds)."""
    now = time.monotonic()
    with _lock:
        _sweep(now, max(window_seconds, 3600))
        q = _hits[key]
        while q and now - q[0] > window_seconds:
            q.popleft()
        if len(q) >= limit:
            return False, max(1, int(window_seconds - (now - q[0])) + 1)
        q.append(now)
        return True, 0


def reset_rate_limits():
    """Clear all counters (used by tests)."""
    with _lock:
        _hits.clear()


def rate_limit(name: str, limit: int, window_seconds: int, by_email: bool = False):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            keys = [f"{name}:ip:{request.remote_addr}"]
            if by_email:
                data = request.get_json(silent=True) or {}
                email = str(data.get("email") or "").strip().lower()[:254]
                if email:
                    keys.append(f"{name}:email:{email}")
            for key in keys:
                allowed, retry_after = check_rate_limit(key, limit, window_seconds)
                if not allowed:
                    resp = jsonify({"error": "Too many attempts. Please try again later."})
                    resp.status_code = 429
                    resp.headers["Retry-After"] = str(retry_after)
                    return resp
            return fn(*args, **kwargs)

        return wrapper

    return decorator
