# Check in / check out (US-10, SRS-10)
from flask import Blueprint, jsonify, request
from middleware.auth_middleware import get_current_user, role_required
from middleware.rate_limit import rate_limit
from models.checkin_model import (CheckinModel,CooldownError,DeliveryError,ValidationError,WrongCodeError)
from models.user_model import STUDENT_ROLES

checkin_bp = Blueprint("checkin", __name__, url_prefix="/api/checkin")
def _iso(value):
    return value.isoformat() if value else None

def _serialize(b: dict) -> dict:
    return {
        "id": b["id"],
        "resource_id": b["resource_id"],
        "resource_name": b.get("resource_name"),
        "resource_code": b.get("resource_code"),
        "resource_status": b.get("resource_status"),
        "purpose": b["purpose"],
        "start_time": _iso(b["start_time"]),
        "end_time": _iso(b["end_time"]),
        "checked_in_at": _iso(b["checked_in_at"]),
        "checked_out_at": _iso(b["checked_out_at"]),
        "can_check_in": "block_reason" in b and b["block_reason"] is None,
        "block_reason": b.get("block_reason"),
    }

def _error(e):
    body = {"error": str(e)}
    status = 400
    if isinstance(e, WrongCodeError):
        body["attempts_left"] = e.attempts_left
    if isinstance(e, CooldownError):
        status = 429
        body["retry_after"] = e.retry_after
    return jsonify(body), status

# The student's approved bookings, split into: in use now / ready to check in / done.
@checkin_bp.get("/mine")
@role_required(*STUDENT_ROLES)
def list_mine():
    data = CheckinModel.list_mine(get_current_user()["id"])
    return jsonify({k: [_serialize(b) for b in v] for k, v in data.items()}), 200

# e-mail a 6-digit code to the student's registered address.
@checkin_bp.post("/<int:booking_id>/code")
@role_required(*STUDENT_ROLES)
@rate_limit("checkin-code", limit=10, window_seconds=900)
def request_code(booking_id):
    try:
        result = CheckinModel.request_code(booking_id, get_current_user())
    except ValidationError as e:
        return _error(e)
    except DeliveryError as e:
        return jsonify({"error": str(e)}), 502
    return jsonify(result), 200

# verify the code; a valid one checks in and sets the resource to "In Use".
@checkin_bp.post("/<int:booking_id>/verify")
@role_required(*STUDENT_ROLES)
@rate_limit("checkin-verify", limit=30, window_seconds=900)
def verify_code(booking_id):
    data = request.get_json(silent=True) or {}
    try:
        booking = CheckinModel.verify_code(booking_id, data.get("code"), get_current_user())
    except ValidationError as e:
        return _error(e)
    return jsonify({"booking": _serialize(booking)}), 200

@checkin_bp.post("/<int:booking_id>/checkout")
@role_required(*STUDENT_ROLES)
def check_out(booking_id):
    try:
        booking = CheckinModel.check_out(booking_id, get_current_user())
    except ValidationError as e:
        return _error(e)
    return jsonify({"booking": _serialize(booking)}), 200