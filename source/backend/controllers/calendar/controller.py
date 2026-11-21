# month calendars
from flask import Blueprint, jsonify, request

from middleware.auth_middleware import get_current_user, login_required, role_required
from models.calendar.model import CalendarModel, ValidationError

calendar_bp = Blueprint("calendar", __name__, url_prefix="/api/calendar")

STAFF_ROLES = ("admin", "professor")


@calendar_bp.get("/resource/<int:resource_id>")
@login_required
def resource_calendar(resource_id):
    user = get_current_user()
    try:
        data = CalendarModel.resource_month(
            resource_id, request.args.get("month"), staff=user["role"] in STAFF_ROLES,
            include_archived=user["role"] == "admin")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    if data is None:
        return jsonify({"error": "Resource not found."}), 404
    return jsonify(data), 200


# only professors see 
@calendar_bp.get("/appointments")
@role_required("professor")
def appointment_calendar():
    try:
        data = CalendarModel.professor_month(get_current_user()["id"], request.args.get("month"))
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(data), 200
