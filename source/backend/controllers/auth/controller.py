import datetime
import jwt
from flask import Blueprint, current_app, jsonify, request
from google.auth.transport import requests as google_requests
from google.auth.exceptions import GoogleAuthError
from google.oauth2 import id_token

from config import Config
from middleware.auth_middleware import password_fingerprint
from middleware.rate_limit import rate_limit
from models.user.model import UserModel, ValidationError
from services.events import service as events  # Iteration 5: failed logins go to the activity log
from services.mailer.service import send_email_in_background

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


_CLOCK_PROBLEM_MARKERS = ("too early", "used too early", "expired", "in the future")


from controllers.auth.issue_token_public_user import _issue_token, _public_user, _is_clock_problem, _verify_google_credential  # noqa: E402
from controllers.auth.google_login_google_complete_profile import google_login, google_complete_profile, me, _send_verification_email, verify_email  # noqa: E402
from controllers.auth.resend_verification_send_reset_email import resend_verification, _send_reset_email, forgot_password  # noqa: E402
from controllers.auth.reset_password import reset_password  # noqa: E402


@auth_bp.post("/signup")
@rate_limit("signup", limit=10, window_seconds=3600)
def signup():
    """Create-account screen: students only, admin/professor added later (SRS-11, URS-9)."""
    data = request.get_json(silent=True) or {}
    try:
        user = UserModel.create_student_account(data)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    # No session yet: the account works only after the emailed link is opened
    try:
        _send_verification_email(user["email"])
    except Exception:
        # The account exists; the user can ask for a fresh link ("Resend verification email")
        current_app.logger.exception("Could not send verification email")
    return jsonify({
        "message": "Account created. Check your email for a verification link, then log in.",
        "email": user["email"],
    }), 201


@auth_bp.post("/login")
@rate_limit("login", limit=10, window_seconds=300, by_email=True)
def login():
    """Email/password login (SRS-11)."""
    data = request.get_json(silent=True) or {}
    email = data.get("email")
    password = data.get("password")
    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400
    if not isinstance(email, str) or not isinstance(password, str):
        return jsonify({"error": "Email and password must be text."}), 400

    user = UserModel.authenticate(email, password)
    if not user:
        events.login_failed(email, ip=request.remote_addr)   # shows up in the activity log
        return jsonify({"error": "Invalid email or password."}), 401
    if not user.get("email_verified", 1):
        # Right password, but the address was never confirmed.
        return jsonify({
            "error": "Please verify your email first. Check your inbox for the verification link.",
            "needs_verification": True,
            "email": user["email"],
        }), 403

    return jsonify({"token": _issue_token(user), "user": _public_user(user)}), 200
