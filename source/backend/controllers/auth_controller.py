import datetime
import jwt
from flask import Blueprint, jsonify, request
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from config import Config
from models.user_model import UserModel, ValidationError
auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# sign up
@auth_bp.post("/signup")
def signup(): # Create-account screen: students only, admin/professor added later (SRS-11, URS-9)
    data = request.get_json(silent=True) or {}
    try:
        user = UserModel.create_student_account(data)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"token": _issue_token(user), "user": _public_user(user)}), 201

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
