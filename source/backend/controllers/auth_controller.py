import datetime

import jwt
from flask import Blueprint, jsonify, request, current_app
from google.auth.transport import requests as google_requests
from google.auth.exceptions import GoogleAuthError
from google.oauth2 import id_token

from config import Config
from middleware.auth_middleware import password_fingerprint
from middleware.rate_limit import rate_limit
from models.user_model import UserModel, ValidationError
from services.mailer import send_email_in_background

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


# jwt helper
def _issue_token(user: dict) -> str:
    payload = {
        "sub": str(user["id"]),
        "email": user["email"],
        "role": user["role"],
        "pwf": password_fingerprint(user.get("password_hash")),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=Config.JWT_EXPIRES_HOURS),
    }
    return jwt.encode(payload, Config.SECRET_KEY, algorithm="HS256")


def _public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "role": user["role"],
        "year": user.get("year"),
    }

_CLOCK_PROBLEM_MARKERS = ("too early", "used too early", "expired", "in the future")

def _is_clock_problem(error: Exception) -> bool:
    text = str(error).lower()
    return any(marker in text for marker in _CLOCK_PROBLEM_MARKERS)

# verify Google ID token
def _verify_google_credential(credential):
    if not credential or not isinstance(credential, str):
        return None, (jsonify({"error": "Missing Google credential."}), 400)

    try:
        payload = id_token.verify_oauth2_token(
            credential, google_requests.Request(), Config.GOOGLE_CLIENT_ID,
            clock_skew_in_seconds=Config.GOOGLE_CLOCK_SKEW_SECONDS,  # small clock drift is tolerated
        )
    except ValueError as e:
        # Check whether the error is related to the device clock
        if _is_clock_problem(e):
            return None, (jsonify({
                "error": "Your Google sign-in is not valid at this moment (it may have expired, or the "
                         "clock on your device may be off). Please check the date and time on your "
                         "device and try signing in again."
            }), 401)
        return None, (jsonify({"error": "Invalid Google token."}), 401)
    except GoogleAuthError:
        # Log the error if Google authentication cannot be completed.
        current_app.logger.exception("Could not verify Google token")
        return None, (jsonify({"error": "Could not verify the Google token right now. Please try again."}), 503)
    
    google_sub = payload.get("sub")
    email = (payload.get("email") or "").strip().lower()
    if not google_sub or not email:
        return None, (jsonify({"error": "Invalid Google token."}), 401)

    # Only trust an email address Google itself has verified; otherwise it
    # could be used to claim (or be linked to) someone else's account.
    if payload.get("email_verified") is not True:
        return None, (jsonify({"error": "Google account email is not verified."}), 403)

    # Server-side domain guard: enforced here regardless of the Cloud
    # project's Audience setting (Internal/External), so a misconfigured
    # consent screen or a personal Gmail account can't slip through.
    allowed_domain = Config.ALLOWED_EMAIL_DOMAIN
    if allowed_domain and not email.endswith("@" + allowed_domain):
        return None, (jsonify({"error": f"Only @{allowed_domain} accounts may sign in."}), 403)

    return {
        "google_sub": google_sub,
        "email": email,
        "full_name": payload.get("name", ""),
    }, None


# signup
@auth_bp.post("/signup")
@rate_limit("signup", limit=10, window_seconds=3600)
def signup(): # Create-account screen: students only, admin/professor added later (SRS-11, URS-9)
    data = request.get_json(silent=True) or {}
    try:
        user = UserModel.create_student_account(data)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    # No session yet: the account works only after the emailed link is opened.
    try:
        _send_verification_email(user["email"])
    except Exception:
        # The account exists; the user can ask for a fresh link ("Resend verification email").
        current_app.logger.exception("Could not send verification email")
    return jsonify({
        "message": "Account created. Check your email for a verification link, then log in.",
        "email": user["email"],
    }), 201


# login
@auth_bp.post("/login")
@rate_limit("login", limit=10, window_seconds=300, by_email=True)
def login(): # Email/password login (SRS-11)
    data = request.get_json(silent=True) or {}
    email = data.get("email")
    password = data.get("password")
    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400
    if not isinstance(email, str) or not isinstance(password, str):
        return jsonify({"error": "Email and password must be text."}), 400

    user = UserModel.authenticate(email, password)
    if not user:
        return jsonify({"error": "Invalid email or password."}), 401
    if not user.get("email_verified", 1):
        # Right password, but the address was never confirmed
        return jsonify({
            "error": "Please verify your email first. Check your inbox for the verification link.",
            "needs_verification": True,
            "email": user["email"],
        }), 403

    return jsonify({"token": _issue_token(user), "user": _public_user(user)}), 200


# google login
@auth_bp.post("/google")
def google_login(): # Verifies the Google ID token from the frontend's OAuth flow (SRS-11)
    data = request.get_json(silent=True) or {}
    identity, error = _verify_google_credential(data.get("credential"))
    if error:
        return error

    google_sub = identity["google_sub"]
    email = identity["email"]
    full_name = identity["full_name"]

    try:
        user, is_new = UserModel.find_or_create_google_user(google_sub, email, full_name)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 403
    # SRS-13: a deactivated account cannot sign in by any method.
    if user and not user["is_active"]:
        return jsonify({"error": "This account has been deactivated."}), 403
    if is_new:
        return jsonify({"needs_role": True, "email": email, "full_name": full_name}), 200

    return jsonify({"token": _issue_token(user), "user": _public_user(user)}), 200


# complete profile
@auth_bp.post("/google/complete-profile")
def google_complete_profile():
    data = request.get_json(silent=True) or {}
    identity, error = _verify_google_credential(data.get("credential"))
    if error:
        return error

    try:
        user = UserModel.complete_google_signup(
            identity["google_sub"], identity["email"], identity["full_name"], data.get("role"),
            year=data.get("year"),
        )
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"token": _issue_token(user), "user": _public_user(user)}), 201


# me endpoint
@auth_bp.get("/me")
def me():
    from middleware.auth_middleware import get_current_user

    user = get_current_user()
    if not user:
        return jsonify({"error": "Not authenticated."}), 401
    return jsonify({"user": _public_user(user)}), 200

# E-mail verification (SRS-11)
def _send_verification_email(to_email: str):
    token = UserModel.create_verification_token(to_email)
    if not token:
        return
    link = f"{Config.APP_BASE_URL}/?verify_token={token}"
    body = (
        f"Welcome to VASE! Click the link below to verify your email:\n\n{link}\n\n"
        f"This link expires in {Config.VERIFY_TOKEN_EXPIRES_MINUTES // 60} hours. "
        "If you didn't create this account, you can ignore this email."
    )
    send_email_in_background(
        to_email,
        "Verify your VASE email",
        body,
        dev_log_line=f"Email verification link for {to_email}: {link}",
    )

@auth_bp.post("/verify-email")
@rate_limit("verify-email", limit=20, window_seconds=900)
def verify_email():
    data = request.get_json(silent=True) or {}
    try:
        UserModel.verify_email(data.get("token"))
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"message": "Email verified. You can now log in."}), 200


@auth_bp.post("/resend-verification")
@rate_limit("resend-verification", limit=5, window_seconds=900, by_email=True)
def resend_verification():
    """Same answer whether or not the address has an unverified account."""
    data = request.get_json(silent=True) or {}
    email = data.get("email")
    if email is not None and not isinstance(email, str):
        return jsonify({"error": "Email must be text."}), 400
    email = (email or "").strip().lower()
    if not email:
        return jsonify({"error": "Email is required."}), 400
    try:
        _send_verification_email(email)
    except Exception:
        current_app.logger.exception("Could not send verification email")
    return jsonify({
        "message": "If this account is waiting for verification, a new link has been sent."
    }), 200


# Forgot Password
def _send_reset_email(to_email: str, reset_link: str):
    body = (
        f"Click the link below to reset your password:\n\n{reset_link}\n\n"
        f"This link expires in {Config.RESET_TOKEN_EXPIRES_MINUTES} minutes. "
        "If you didn't request this, you can ignore this email."
    )
    # Send the email in the background to avoid delaying the response.
    # If SMTP_HOST is not set, print the link to the server log instead.
    send_email_in_background(
        to_email,
        "Reset your VASE password",
        body,
        dev_log_line=f"Password reset link for {to_email}: {reset_link}",
    )

@auth_bp.post("/forgot-password")
@rate_limit("forgot-password", limit=5, window_seconds=900, by_email=True)
def forgot_password():
    data = request.get_json(silent=True) or {}
    email = data.get("email")
    if email is not None and not isinstance(email, str):
        return jsonify({"error": "Email must be text."}), 400
    email = (email or "").strip().lower()
    if not email:
        return jsonify({"error": "Email is required."}), 400

    token = UserModel.create_reset_token(email)
    if token:
        reset_link = f"{Config.APP_BASE_URL}/?reset_token={token}"
        try:
            _send_reset_email(email, reset_link)
        except Exception:
            # Keep the response the same even if sending the email fails.
            current_app.logger.exception("Could not send password reset email")

    return jsonify(
        {"message": "If an account exists for this email, a reset link has been sent."}
    ), 200


@auth_bp.post("/reset-password")
@rate_limit("reset-password", limit=10, window_seconds=900)
def reset_password():
# Completes a reset using the single-use, time-limited token from the emailed link
    data = request.get_json(silent=True) or {}
    token = data.get("token")
    new_password = data.get("password")
    if not token:
        return jsonify({"error": "Missing reset token."}), 400

    try:
        UserModel.reset_password(token, new_password)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({"message": "Password updated. You can now log in."}), 200
