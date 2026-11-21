from flask import Blueprint, jsonify, request

from middleware.auth_middleware import role_required
from models.dashboard.model import DashboardModel, ValidationError, resolve_period

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/api/dashboard")

VIEWER_ROLES = ("admin", "professor")


@dashboard_bp.get("")
@role_required(*VIEWER_ROLES)
def dashboard():
    args = request.args
    try:
        start, end = resolve_period(args.get("days"), args.get("from"), args.get("to"))
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(DashboardModel.summary(start, end)), 200
