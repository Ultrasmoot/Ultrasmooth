import datetime
import jwt
from flask import Blueprint, jsonify, request
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from config import Config
from models.user_model import UserModel, ValidationError
auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")