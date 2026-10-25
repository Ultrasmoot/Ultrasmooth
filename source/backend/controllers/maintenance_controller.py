from flask import Blueprint, jsonify, request
from middleware.auth_middleware import get_current_user, login_required, role_required
from models.maintenance_model import MaintenanceModel, ValidationError

maintenance_bp = Blueprint("maintenance", __name__, url_prefix="/api/maintenance")

def _iso(value):
    return value.isoformat() if value else None


def _serialize(m: dict) -> dict:
    return {
        "id": m["id"],
        "resource_id": m["resource_id"],
        "resource_name": m.get("resource_name"),
        "resource_code": m.get("resource_code"),
        "reported_by": m["reported_by"],
        "reporter_name": m.get("reporter_name"),
        "reporter_email": m.get("reporter_email"),
        "description": m["description"],
        "status": m["status"],
        "issue_date": _iso(m["issue_date"]),
        "confirmed_by": m["confirmed_by"],
        "confirmed_at": _iso(m["confirmed_at"]),
        "closed_by": m["closed_by"],
        "closed_at": _iso(m["closed_at"]),
        "dismiss_reason": m.get("dismiss_reason"),
    }


@maintenance_bp.post("")
@login_required
def report_issue():
    data = request.get_json(silent=True) or {}
    user = get_current_user()
    try:
        record = MaintenanceModel.report(data, reporter=user)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"record": _serialize(record)}), 201


@maintenance_bp.get("")
@login_required
def list_records():
    user = get_current_user()
    records = MaintenanceModel.list(
        user,
        status_group=request.args.get("group"),
        resource_id=request.args.get("resource_id", type=int),
    )
    return jsonify({"records": [_serialize(r) for r in records]}), 200


@maintenance_bp.get("/<int:record_id>")
@login_required
def get_record(record_id):
    user = get_current_user()
    record = MaintenanceModel.get(record_id)
    # A non-admin asking for someone else's report gets the same 404 as a missing one.
    if not record or (user["role"] != "admin" and record["reported_by"] != user["id"]):
        return jsonify({"error": "Maintenance record not found."}), 404
    return jsonify({"record": _serialize(record)}), 200


def _admin_action(fn, record_id, *args):
    try:
        record = fn(record_id, *args)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"record": _serialize(record)}), 200


# Admin-only: confirm a report (resource -> Maintenance) or dismiss it.
@maintenance_bp.post("/<int:record_id>/confirm")
@role_required("admin")
def confirm_record(record_id):
    return _admin_action(MaintenanceModel.confirm, record_id, get_current_user()["id"])


@maintenance_bp.post("/<int:record_id>/dismiss")
@role_required("admin")
def dismiss_record(record_id):
    # "Reject" in the UI. A reason is required and is shown to the person who reported it.
    data = request.get_json(silent=True) or {}
    return _admin_action(MaintenanceModel.dismiss, record_id, get_current_user()["id"], data.get("reason"))


@maintenance_bp.put("/<int:record_id>")
@role_required("admin")
def update_record(record_id):
    data = request.get_json(silent=True) or {}
    return _admin_action(MaintenanceModel.update, record_id, data)


@maintenance_bp.post("/<int:record_id>/resolve")
@role_required("admin")
def resolve_record(record_id):
    return _admin_action(MaintenanceModel.resolve, record_id, get_current_user()["id"])