import controllers.auth.controller as _m

@_m.auth_bp.post("/resend-verification")
@_m.rate_limit("resend-verification", limit=5, window_seconds=900, by_email=True)
def resend_verification():
    # same answer whether or not the address has an unverified account
    data = _m.request.get_json(silent=True) or {}
    email = data.get("email")
    if email is not None and not isinstance(email, str):
        return _m.jsonify({"error": "Email must be text."}), 400
    email = (email or "").strip().lower()
    if not email:
        return _m.jsonify({"error": "Email is required."}), 400
    try:
        _m._send_verification_email(email)
    except Exception:
        _m.current_app.logger.exception("Could not send verification email")
    return _m.jsonify({
        "message": "If this account is waiting for verification, a new link has been sent."
    }), 200

# forgot password
def _send_reset_email(to_email: str, reset_link: str):
    body = (
        f"Click the link below to reset your password:\n\n{reset_link}\n\n"
        f"This link expires in {_m.Config.RESET_TOKEN_EXPIRES_MINUTES} minutes. "
        "If you didn't request this, you can ignore this email."
    )
    # mailer
    _m.send_email_in_background(
        to_email,
        "Reset your VASE password",
        body,
        dev_log_line=f"Password reset link for {to_email}: {reset_link}",
    )

@_m.auth_bp.post("/forgot-password")
@_m.rate_limit("forgot-password", limit=5, window_seconds=900, by_email=True)
def forgot_password():
    # requests a reset link. Always responds the same way regardless of
    # whether the email exists, to avoid revealing which emails have accounts
    data = _m.request.get_json(silent=True) or {}
    email = data.get("email")
    if email is not None and not isinstance(email, str):
        return _m.jsonify({"error": "Email must be text."}), 400
    email = (email or "").strip().lower()
    if not email:
        return _m.jsonify({"error": "Email is required."}), 400

    token = _m.UserModel.create_reset_token(email)
    if token:
        reset_link = f"{_m.Config.APP_BASE_URL}/?reset_token={token}"
        try:
            _m._send_reset_email(email, reset_link)
        except Exception:
            # A mail failure must not change the response: a 500 here would
            # reveal which emails have accounts.
            _m.current_app.logger.exception("Could not send password reset email")

    return _m.jsonify(
        {"message": "If an account exists for this email, a reset link has been sent."}
    ), 200
