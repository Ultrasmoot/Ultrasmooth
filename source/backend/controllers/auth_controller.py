import datetime
import smtplib
from email.mime.text import MIMEText

import jwt
from flask import Blueprint, jsonify, request
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from config import Config
from middleware.rate_limit import rate_limit
from models.user_model import UserModel, ValidationError

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


# jwt helper
def _issue_token(user: dict) -> str:
    payload = {
        "sub": user["id"],
        "email": user["email"],
        "role": user["role"],
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=Config.JWT_EXPIRES_HOURS),
    }
    return jwt.encode(payload, Config.SECRET_KEY, algorithm="HS256")


def _public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "role": user["role"],
    }


# verify Google ID token
def _verify_google_credential(credential):
    if not credential or not isinstance(credential, str):
        return None, (jsonify({"error": "Missing Google credential."}), 400)

    try:
        payload = id_token.verify_oauth2_token(
            credential, google_requests.Request(), Config.GOOGLE_CLIENT_ID
        )
    except ValueError:
        return None, (jsonify({"error": "Invalid Google token."}), 401)

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
    return jsonify({"token": _issue_token(user), "user": _public_user(user)}), 201


# login
@auth_bp.post("/login")
@rate_limit("login", limit=10, window_seconds=300, by_email=True)
def login(): # Email/password login (SRS-11)
    data = request.get_json(silent=True) or {}
    email = data.get("email")
    password = data.get("password")
    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400

    user = UserModel.authenticate(email, password)
    if not user:
        return jsonify({"error": "Invalid email or password."}), 401

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

    user, is_new = UserModel.find_or_create_google_user(google_sub, email, full_name)
    if is_new:
        # First-time Google sign-in: ask for a role before creating the account.
        # google_sub is intentionally NOT returned: the client must send the
        # Google credential again to complete sign-up (see complete-profile).
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
            identity["google_sub"], identity["email"], identity["full_name"], data.get("role")
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


# Forgot Password
def _send_reset_email(to_email: str, reset_link: str):
    subject = "Reset your VASE password"
    body = (
        f"Click the link below to reset your password:\n\n{reset_link}\n\n"
        f"This link expires in {Config.RESET_TOKEN_EXPIRES_MINUTES} minutes. "
        "If you didn't request this, you can ignore this email."
    )

    if not Config.SMTP_HOST:
        print(f"[DEV] Password reset link for {to_email}: {reset_link}")
        return

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = Config.SMTP_FROM
    msg["To"] = to_email

    with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT) as server:
        server.starttls()
        server.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
        server.sendmail(Config.SMTP_FROM, [to_email], msg.as_string())


@auth_bp.post("/forgot-password")
@rate_limit("forgot-password", limit=5, window_seconds=900, by_email=True)
def forgot_password():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not email:
        return jsonify({"error": "Email is required."}), 400

    token = UserModel.create_reset_token(email)
    if token:
        reset_link = f"{Config.APP_BASE_URL}/?reset_token={token}"
        _send_reset_email(email, reset_link)

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
