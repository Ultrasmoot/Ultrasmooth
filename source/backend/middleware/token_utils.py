import hashlib
import hmac
import jwt
import re
import middleware.auth_middleware as _m

def password_fingerprint(password_hash) -> str:
    return hmac.new(
        _m.Config.SECRET_KEY.encode("utf-8"),
        (password_hash or "").encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]

def _decode_token():
    auth_header = _m.request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ", 1)[1]
    try:
        # Tokens we issue carry a string sub, but a token issued earlier with an
        # int sub must still be judged by get_current_user() (int() below plus the
        # password fingerprint), not fail here depending on the PyJWT version.
        return jwt.decode(
            token, _m.Config.SECRET_KEY, algorithms=["HS256"], options={"verify_sub": False}
        )
    except jwt.PyJWTError:
        return None

def get_current_user():
    # cached per-request lookup of the authenticated user (or None)
    if hasattr(_m.g, "current_user"):
        return _m.g.current_user
    claims = _m._decode_token()
    if not claims:
        _m.g.current_user = None
        return None
    # for tokens issued earlier. Booleans, floats and non-numeric text are not
    sub = claims.get("sub")
    if isinstance(sub, bool) or not (
        isinstance(sub, int) or (isinstance(sub, str) and re.fullmatch(r"\d{1,18}", sub))
    ):
        _m.g.current_user = None
        return None
    user_id = int(sub)
    user = _m.UserModel.find_by_id(user_id)
    if user:
        token_pwf = claims.get("pwf")
        current_pwf = _m.password_fingerprint(user.get("password_hash"))
        if not isinstance(token_pwf, str) or not hmac.compare_digest(token_pwf, current_pwf):
            user = None  # password changed since this token was issued
    _m.g.current_user = user if user and user["is_active"] else None
    return _m.g.current_user

def login_required(fn):
    @_m.wraps(fn)
    def wrapper(*args, **kwargs):
        if not _m.get_current_user():
            return _m.jsonify({"error": "Authentication required."}), 401
        return fn(*args, **kwargs)

    return wrapper
