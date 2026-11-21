import datetime
import jwt
import controllers.auth.controller as _m

# jwt helper
def _issue_token(user: dict) -> str:
    payload = {
        "sub": str(user["id"]),
        "email": user["email"],
        "role": user["role"],
        "pwf": _m.password_fingerprint(user.get("password_hash")),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=_m.Config.JWT_EXPIRES_HOURS),
    }
    return jwt.encode(payload, _m.Config.SECRET_KEY, algorithm="HS256")

def _public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "role": user["role"],
        "year": user.get("year"),
    }

def _is_clock_problem(error: Exception) -> bool:
    text = str(error).lower()
    return any(marker in text for marker in _m._CLOCK_PROBLEM_MARKERS)

# verify Google ID token
def _verify_google_credential(credential):
    if not credential or not isinstance(credential, str):
        return None, (_m.jsonify({"error": "Missing Google credential."}), 400)

    try:
        payload = _m.id_token.verify_oauth2_token(
            credential,
            _m.google_requests.Request(),
            _m.Config.GOOGLE_CLIENT_ID,
            clock_skew_in_seconds=_m.Config.GOOGLE_CLOCK_SKEW_SECONDS,
        )
    except ValueError as e:
        # google-auth reports a clock problem as a ValueError too. 
        if _m._is_clock_problem(e):
            return None, (_m.jsonify({
                "error": "Your Google sign-in is not valid at this moment (it may have expired, or the "
                         "clock on your device may be off). Please check the date and time on your "
                         "device and try signing in again."
            }), 401)
        return None, (_m.jsonify({"error": "Invalid Google token."}), 401)
    except _m.GoogleAuthError:
        # Google's signing certificates could not be fetched
        # Report it as a temporary failure, not a 500.
        _m.current_app.logger.exception("Could not verify Google token")
        return None, (_m.jsonify({"error": "Could not verify the Google token right now. Please try again."}), 503)

    google_sub = payload.get("sub")
    email = (payload.get("email") or "").strip().lower()
    if not google_sub or not email:
        return None, (_m.jsonify({"error": "Invalid Google token."}), 401)

    # Only trust an email address Google itself has verified; otherwise it
    # could be used to claim (or be linked to) someone else's account.
    if payload.get("email_verified") is not True:
        return None, (_m.jsonify({"error": "Google account email is not verified."}), 403)

    # Server-side domain guard: enforced here regardless of the Cloud
    # project's Audience setting (Internal/External), so a misconfigured
    # consent screen or a personal Gmail account can't slip through.
    allowed_domain = _m.Config.ALLOWED_EMAIL_DOMAIN
    if allowed_domain and not email.endswith("@" + allowed_domain):
        return None, (_m.jsonify({"error": f"Only @{allowed_domain} accounts may sign in."}), 403)

    return {
        "google_sub": google_sub,
        "email": email,
        "full_name": payload.get("name", ""),
    }, None
