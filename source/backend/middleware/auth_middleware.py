import hashlib
import hmac
import re
from functools import wraps

import jwt
from flask import g, jsonify, request

from config import Config
from models.user.model import UserModel


from middleware.token_utils import password_fingerprint, _decode_token, get_current_user, login_required  # noqa: E402


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
