from flask import Blueprint, jsonify, request

from middleware.auth_middleware import get_current_user, login_required, role_required
from models.maintenance.model import MaintenanceModel, ValidationError as MaintenanceValidationError
from models.resource_detail.model import ResourceDetailModel
from models.resource.model import ResourceModel, ValidationError

resource_bp = Blueprint("resources", __name__, url_prefix="/api/resources")


from controllers.resource.serialize_list_resources import _serialize, list_resources, get_resource, resource_detail, create_resource 


@resource_bp.put("/<int:resource_id>")
@role_required("admin")
def update_resource(resource_id):
    """SRS-2: only Lab Managers/Administrators may edit resource records."""
    data = request.get_json(silent=True) or {}
    try:
        resource = ResourceModel.update(resource_id, data, actor_id=get_current_user()["id"])
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"resource": _serialize(resource)}), 200


@resource_bp.post("/<int:resource_id>/archive")
@role_required("admin")
def archive_resource(resource_id):
    """SRS-2 / AD-1: archiving hides a resource from the active list rather than deleting it."""
    try:
        ResourceModel.archive(resource_id, actor_id=get_current_user()["id"])
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"status": "archived"}), 200


@resource_bp.post("/<int:resource_id>/unarchive")
@role_required("admin")
def unarchive_resource(resource_id):
    """Reverse of archive: puts the resource back on the active list."""
    try:
        ResourceModel.unarchive(resource_id, actor_id=get_current_user()["id"])
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"status": "unarchived"}), 200


@resource_bp.post("/<int:resource_id>/restore")
@role_required("admin")
def restore_resource(resource_id):
    """SRS-7: an administrator returns a resource from Maintenance to Available.
    Any Open / In Progress issues of the resource are resolved at the same time."""
    try:
        closed = MaintenanceModel.release_resource(resource_id, get_current_user()["id"])
    except MaintenanceValidationError as e:
        return jsonify({"error": str(e)}), 400
    resource = ResourceModel.get(resource_id)
    return jsonify({"resource": _serialize(resource), "closed_issues": closed}), 200
