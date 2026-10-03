from flask import Blueprint, jsonify, request

from middleware.auth_middleware import login_required, role_required, get_current_user
from models.booking_model import BookingModel, ValidationError
from models.user_model import STUDENT_ROLES

booking_bp = Blueprint("bookings", __name__, url_prefix="/api/bookings")

def _serialize(b: dict) -> dict:
    return {
        "id": b["id"],
        "resource_id": b["resource_id"],
        "resource_name": b.get("resource_name"),
        "requester_id": b["requester_id"],
        "requester_name": b.get("requester_name"),
        "requester_email": b.get("requester_email"),
        "start_time": b["start_time"].isoformat(),
        "end_time": b["end_time"].isoformat(),
        "purpose": b["purpose"],
        "status": b["status"],
        "decided_by": b["decided_by"],
        "decided_at": b["decided_at"].isoformat() if b["decided_at"] else None,
    }


# US-3: Ph.D. Students and Undergraduate Students submit a booking request.
@booking_bp.post("")
@role_required(*STUDENT_ROLES)
def create_booking():
    data = request.get_json(silent=True) or {}
    user = get_current_user()
    try:
        booking = BookingModel.create(data, requester_id=user["id"])
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"booking": _serialize(booking)}), 201

# US-4: a requester views their own bookings and current status.
@booking_bp.get("/mine")
@login_required
def list_my_bookings():
    user = get_current_user()
    bookings = BookingModel.list_mine(user["id"])
    return jsonify({"bookings": [_serialize(b) for b in bookings]}), 200

# US-5: Lab Managers/Administrators can view the pending queue.
@booking_bp.get("/pending")
@role_required("admin")
def list_pending_bookings():
    bookings = BookingModel.list_pending()
    return jsonify({"bookings": [_serialize(b) for b in bookings]}), 200


# admin history: already-decided requests
@booking_bp.get("/history")
@role_required("admin")
def list_booking_history():
    bookings = BookingModel.list_history()
    return jsonify({"bookings": [_serialize(b) for b in bookings]}), 200


# US-5: Lab Managers/Administrators can approve or reject a request
@booking_bp.post("/<int:booking_id>/decide")
@role_required("admin")
def decide_booking(booking_id):
    data = request.get_json(silent=True) or {}
    user = get_current_user()
    try:
        booking = BookingModel.decide(booking_id, data.get("decision"), admin_id=user["id"])
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"booking": _serialize(booking)}), 200
