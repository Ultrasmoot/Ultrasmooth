from functools import wraps
from config import Config
from models.user_model import UserModel
import jwt
from flask import g, jsonify, request

def _decode_token():
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ", 1)[1]
    try:
        return jwt.decode(token, Config.SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None

def get_current_user(): # Cached per-request lookup of the authenticated user (or None)
    if hasattr(g, "current_user"):
        return g.current_user
    claims = _decode_token()
    if not claims:
        g.current_user = None
        return None
    user = UserModel.find_by_id(claims["sub"])
    g.current_user = user if user and user["is_active"] else None
    return g.current_user

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not get_current_user():
            return jsonify({"error": "Authentication required."}), 401
        return fn(*args, **kwargs)
    return wrapper

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
