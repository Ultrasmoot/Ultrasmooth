import controllers.auth.controller as _m

@_m.auth_bp.post("/reset-password")
@_m.rate_limit("reset-password", limit=10, window_seconds=900)
def reset_password():
    # completes a reset using the single-use, time-limited token from the emailed link
    data = _m.request.get_json(silent=True) or {}
    token = data.get("token")
    new_password = data.get("password")
    if not token:
        return _m.jsonify({"error": "Missing reset token."}), 400

    try:
        _m.UserModel.reset_password(token, new_password)
    except _m.ValidationError as e:
        return _m.jsonify({"error": str(e)}), 400

    return _m.jsonify({"message": "Password updated. You can now log in."}), 200
