# User & Access management (US-13). Every route is administrator-only; the role is
# checked on the server by role_required, so hiding the menu item in the UI is not the protection
from flask import Blueprint, jsonify, request

from middleware.auth_middleware import get_current_user, role_required
from models.user_admin_model import NotFoundError, UserAdminModel
from models.user_model import ValidationError

user_admin_bp = Blueprint("user_admin", __name__, url_prefix="/api/admin/users")


def _fail(e):
    return jsonify({"error": str(e)}), (404 if isinstance(e, NotFoundError) else 400)


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


@user_admin_bp.get("")
@role_required("admin")
def list_users():
    try:
        users = UserAdminModel.list_users(
            query=request.args.get("q"), role=request.args.get("role"), status=request.args.get("status"))
    except ValidationError as e:
        return _fail(e)
    return jsonify({"users": users, "total": len(users)}), 200


@user_admin_bp.post("")
@role_required("admin")
def create_user():
    data = _body()
    if data is None:
        return _fail(ValidationError("A JSON body is required."))
    try:
        user = UserAdminModel.create(get_current_user()["id"], data)
    except ValidationError as e:
        return _fail(e)
    return jsonify({"user": user}), 201


@user_admin_bp.put("/<int:user_id>")
@role_required("admin")
def update_user(user_id):
    data = _body()
    if data is None:
        return _fail(ValidationError("A JSON body is required."))
    try:
        user = UserAdminModel.update(get_current_user()["id"], user_id, data)
    except ValidationError as e:
        return _fail(e)
    return jsonify({"user": user}), 200


@user_admin_bp.post("/<int:user_id>/deactivate")
@role_required("admin")
def deactivate_user(user_id):
    try:
        user = UserAdminModel.set_active(get_current_user()["id"], user_id, False)
    except ValidationError as e:
        return _fail(e)
    return jsonify({"user": user}), 200


@user_admin_bp.post("/<int:user_id>/reactivate")
@role_required("admin")
def reactivate_user(user_id):
    try:
        user = UserAdminModel.set_active(get_current_user()["id"], user_id, True)
    except ValidationError as e:
        return _fail(e)
    return jsonify({"user": user}), 200
