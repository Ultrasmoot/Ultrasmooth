import controllers.auth.controller as _m

# google login
@_m.auth_bp.post("/google")
def google_login():
    # verifies the Google ID token from the frontend's OAuth flow
    data = _m.request.get_json(silent=True) or {}
    identity, error = _m._verify_google_credential(data.get("credential"))
    if error:
        return error

    google_sub = identity["google_sub"]
    email = identity["email"]
    full_name = identity["full_name"]

    try:
        user, is_new = _m.UserModel.find_or_create_google_user(google_sub, email, full_name)
    except _m.ValidationError as e:
        # this e-mail already belongs to an account linked to a DIFFERENT Google identity
        return _m.jsonify({"error": str(e)}), 403
    # a deactivated account cannot sign in by any method.
    if user and not user["is_active"]:
        return _m.jsonify({"error": "This account has been deactivated."}), 403
    if is_new:
        # ask for a role before creating the account , the client must send the
        # Google credential again to complete sign-up (see complete-profile)
        return _m.jsonify({"needs_role": True, "email": email, "full_name": full_name}), 200

    return _m.jsonify({"token": _m._issue_token(user), "user": _m._public_user(user)}), 200

# complete profile
@_m.auth_bp.post("/google/complete-profile")
def google_complete_profile():
    # a first-time Google sign-up once the user picks a role.
    # The Google ID token is re-verified here; google_sub, email and name come
    # from the verified token only, never from the request body
    data = _m.request.get_json(silent=True) or {}
    identity, error = _m._verify_google_credential(data.get("credential"))
    if error:
        return error

    try:
        user = _m.UserModel.complete_google_signup(
            identity["google_sub"], identity["email"], identity["full_name"], data.get("role"),
            year=data.get("year"),
        )
    except _m.ValidationError as e:
        return _m.jsonify({"error": str(e)}), 400
    return _m.jsonify({"token": _m._issue_token(user), "user": _m._public_user(user)}), 201

# me endpoint
@_m.auth_bp.get("/me")
def me():
    from middleware.auth_middleware import get_current_user

    user = get_current_user()
    if not user:
        return _m.jsonify({"error": "Not authenticated."}), 401
    return _m.jsonify({"user": _m._public_user(user)}), 200

# E-mail verification
def _send_verification_email(to_email: str):
    token = _m.UserModel.create_verification_token(to_email)
    if not token:
        return
    link = f"{_m.Config.APP_BASE_URL}/?verify_token={token}"
    body = (
        f"Welcome to VASE! Click the link below to verify your email:\n\n{link}\n\n"
        f"This link expires in {_m.Config.VERIFY_TOKEN_EXPIRES_MINUTES // 60} hours. "
        "If you didn't create this account, you can ignore this email."
    )
    _m.send_email_in_background(
        to_email,
        "Verify your VASE email",
        body,
        dev_log_line=f"Email verification link for {to_email}: {link}",
    )

@_m.auth_bp.post("/verify-email")
@_m.rate_limit("verify-email", limit=20, window_seconds=900)
def verify_email():
    data = _m.request.get_json(silent=True) or {}
    try:
        _m.UserModel.verify_email(data.get("token"))
    except _m.ValidationError as e:
        return _m.jsonify({"error": str(e)}), 400
    return _m.jsonify({"message": "Email verified. You can now log in."}), 200
