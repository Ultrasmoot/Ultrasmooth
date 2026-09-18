from flask import Blueprint, jsonify, request

from middleware.auth_middleware import login_required, role_required
from models.resource_model import ResourceModel, ValidationError

resource_bp = Blueprint("resources", __name__, url_prefix="/api/resources")

# add dic to collect data
def _serialize(r: dict) -> dict:
    return {
        "id": r["id"],
        "resource_code": r["resource_code"],
        "name": r["name"],
        "type": r["type"],
        "category": r["category"],
        "location": r["location"],
        "owner": r["owner"],
        "status": r["status"],
        "is_archived": bool(r["is_archived"]),
    }


@resource_bp.get("")
@login_required
def list_resources():
    """SRS-1: view/search resources. Available to every authenticated role
    (Ph.D./Undergrad Student, Lab Manager/Administrator, Professor)."""
    search = request.args.get("q")
    category = request.args.get("category")
    location = request.args.get("location")
    status = request.args.get("status")
    include_archived = request.args.get("include_archived") == "true"
    sort_by = request.args.get("sort", "name")
    sort_dir = request.args.get("dir", "asc")

    from middleware.auth_middleware import get_current_user
    user = get_current_user()
    # only admins can see archived resources
    if include_archived and user["role"] != "admin":
        include_archived = False

    resources = ResourceModel.list(
        search=search, category=category, location=location,
        status=status, include_archived=include_archived,
        sort_by=sort_by, sort_dir=sort_dir,
    )
    return jsonify({"resources": [_serialize(r) for r in resources]}), 200


@resource_bp.get("/<int:resource_id>")
@login_required
def get_resource(resource_id):
    resource = ResourceModel.get(resource_id)
    if not resource:
        return jsonify({"error": "Resource not found."}), 404
    return jsonify({"resource": _serialize(resource)}), 200


@resource_bp.post("")
@role_required("admin")
def create_resource(): # SRS-2: only Lab Managers/Administrators may add resource records
    data = request.get_json(silent=True) or {}
    try:
        resource = ResourceModel.create(data)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"resource": _serialize(resource)}), 201


@resource_bp.put("/<int:resource_id>")
@role_required("admin")
def update_resource(resource_id): # SRS-2: only Lab Managers/Administrators may edit resource records
    data = request.get_json(silent=True) or {}
    try:
        resource = ResourceModel.update(resource_id, data)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"resource": _serialize(resource)}), 200

@resource_bp.post("/<int:resource_id>/archive")
@role_required("admin")
def archive_resource(resource_id):
    """SRS-2 / AD-1: archiving hides a resource from the active list rather than deleting it."""
    try:
        ResourceModel.archive(resource_id)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"status": "archived"}), 200