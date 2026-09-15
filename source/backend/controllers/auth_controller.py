import datetime
import jwt
from flask import Blueprint, jsonify, request
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from config import Config
from models.user_model import UserModel, ValidationError
auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

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

# sign up
@auth_bp.post("/signup")
def signup(): # Create-account screen: students only, admin/professor added later (SRS-11, URS-9)
    data = request.get_json(silent=True) or {}
    try:
        user = UserModel.create_student_account(data)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"token": _issue_token(user), "user": _public_user(user)}), 201

# login
@auth_bp.post("/login")
def login():
    # email-password login (SRS-11)
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
def google_login(): # check google id token from the frontend
    data = request.get_json(silent=True) or {}
    credential = data.get("credential")
    if not credential:
        return jsonify({"error": "Missing Google credential."}), 400

    try:
        payload = id_token.verify_oauth2_token(
            credential, google_requests.Request(), Config.GOOGLE_CLIENT_ID
        )
    except ValueError:
        return jsonify({"error": "Invalid Google token."}), 401

    google_sub = payload["sub"]
    email = (payload.get("email") or "").lower()
    full_name = payload.get("name", "")

    # check the email is from the allowed domain
    allowed_domain = Config.ALLOWED_EMAIL_DOMAIN
    if allowed_domain and not email.endswith("@" + allowed_domain):
        return jsonify({"error": f"Only @{allowed_domain} accounts may sign in."}), 403

    user, is_new = UserModel.find_or_create_google_user(google_sub, email, full_name)
    if is_new:
        # new google user needs to choose a role first
        return jsonify(
            {"needs_role": True, "google_sub": google_sub, "email": email, "full_name": full_name}
        ), 200

    return jsonify({"token": _issue_token(user), "user": _public_user(user)}), 200

# google complete profile
@auth_bp.post("/google/complete-profile")
def google_complete_profile(): # Finishes a first-time Google sign-up once the user picks a role
    data = request.get_json(silent=True) or {}
    try:
        user = UserModel.complete_google_signup(data.get("google_sub"), data.get("email"), data.get("full_name"), data.get("role"))
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"token": _issue_token(user), "user": _public_user(user)}), 201

# me/end point
@auth_bp.get("/me")
def me():
    from middleware.auth_middleware import get_current_user

    user = get_current_user()
    if not user:
        return jsonify({"error": "Not authenticated."}), 401
    return jsonify({"user": _public_user(user)}), 200
