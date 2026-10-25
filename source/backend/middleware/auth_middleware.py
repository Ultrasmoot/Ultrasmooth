import hashlib
import hmac
import re
from functools import wraps
import jwt
from flask import g, jsonify, request
from config import Config
from models.user_model import UserModel

def password_fingerprint(password_hash) -> str:
    return hmac.new(
        Config.SECRET_KEY.encode("utf-8"),
        (password_hash or "").encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]

def _decode_token():
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ", 1)[1]
    try:
        return jwt.decode(
            token, Config.SECRET_KEY, algorithms=["HS256"], options={"verify_sub": False}
        )
    except jwt.PyJWTError:
        return None

def get_current_user():
    # Cached per-request lookup of the authenticated user (or None)
    if hasattr(g, "current_user"):
        return g.current_user
    claims = _decode_token()
    if not claims:
        g.current_user = None
        return None
    sub = claims.get("sub")
    if isinstance(sub, bool) or not (
        isinstance(sub, int) or (isinstance(sub, str) and re.fullmatch(r"\d{1,18}", sub))
    ):
        g.current_user = None
        return None
    user_id = int(sub)
    user = UserModel.find_by_id(user_id)
    if user:
        token_pwf = claims.get("pwf")
        current_pwf = password_fingerprint(user.get("password_hash"))
        if not isinstance(token_pwf, str) or not hmac.compare_digest(token_pwf, current_pwf):
            user = None  # password changed since this token was issued
    g.current_user = user if user and user["is_active"] else None
    return g.current_user

def role_required(*allowed_roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if not user:
                return jsonify({"error": "Authentication required."}), 401
            if user["role"] not in allowed_roles:
                return jsonify({"error": "Access denied for your role."}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator