import datetime

from flask import Blueprint, jsonify, request

from middleware.auth_middleware import get_current_user, role_required
from middleware.rate_limit import rate_limit
from models.appointment_model import AppointmentModel, ValidationError
from models.user_model import STUDENT_ROLES

appointment_bp = Blueprint("appointments", __name__, url_prefix="/api/appointments")


def _iso(value):
    return value.isoformat() if value else None


def _serialize(a: dict) -> dict:
    return {
        "id": a["id"],
        "professor_id": a["professor_id"],
        "professor_name": a["professor_name"],
        "student_id": a["student_id"],
        "student_name": a["student_name"],
        "topic": a["topic"],
        "details": a["details"],
        "start_time": _iso(a["start_time"]),
        "end_time": _iso(a["end_time"]),
        "status": a["status"],
        "expired": a["status"] == "Pending" and a["start_time"] <= datetime.datetime.now(),
        "decision_reason": a["decision_reason"],
        "decided_at": _iso(a["decided_at"]),
    }


def _fail(e):
    return jsonify({"error": str(e)}), 400


@appointment_bp.get("/professors")
@role_required(*STUDENT_ROLES)
def professors():
    return jsonify({"professors": [
        {"id": p["id"], "name": p["full_name"],
         "expertise": [e.strip() for e in p["expertise"].split(",") if e.strip()],
         "bio": p["bio"], "photo_url": None}
        for p in AppointmentModel.professors()
    ]}), 200


@appointment_bp.post("")
@role_required(*STUDENT_ROLES)
@rate_limit("appointment-request", limit=20, window_seconds=3600)
def request_appointment():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _fail(ValidationError("A JSON body is required."))
    try:
        appt = AppointmentModel.request(get_current_user()["id"], data)
    except ValidationError as e:
        return _fail(e)
    return jsonify({"appointment": _serialize(appt)}), 201


@appointment_bp.get("/mine")
@role_required(*STUDENT_ROLES)
def my_appointments():
    rows = AppointmentModel.list_for_student(get_current_user()["id"])
    return jsonify({"appointments": [_serialize(a) for a in rows]}), 200


@appointment_bp.get("/inbox")
@role_required("professor")
def inbox():
    rows = AppointmentModel.list_for_professor(get_current_user()["id"])
    return jsonify({"appointments": [_serialize(a) for a in rows]}), 200


@appointment_bp.post("/<int:appt_id>/decide")
@role_required("professor")
def decide(appt_id):
    data = request.get_json(silent=True)
    data = data if isinstance(data, dict) else {}
    try:
        appt = AppointmentModel.decide(appt_id, get_current_user()["id"], data.get("decision"), data.get("reason"))
    except ValidationError as e:
        return _fail(e)
    return jsonify({"appointment": _serialize(appt)}), 200


@appointment_bp.post("/<int:appt_id>/cancel")
@role_required(*STUDENT_ROLES)
def cancel(appt_id):
    try:
        appt = AppointmentModel.cancel(appt_id, get_current_user()["id"])
    except ValidationError as e:
        return _fail(e)
    return jsonify({"appointment": _serialize(appt)}), 200
