from flask import Blueprint, jsonify, request

from middleware.auth_middleware import login_required, role_required, get_current_user
from models.announcement_model import AnnouncementModel, ValidationError, POSTER_ROLES

announcement_bp = Blueprint("announcements", __name__, url_prefix="/api/announcements")

def _serialize(a: dict) -> dict:
    return {
        "id": a["id"],
        "author_id": a["author_id"],
        "title": a["title"],
        "body": a["body"],
        "is_pinned": bool(a["is_pinned"]),
        "created_at": a["created_at"].isoformat(),
    }

@announcement_bp.get("")
@login_required
def list_announcements():
    items = AnnouncementModel.list()
    return jsonify({"announcements": [_serialize(a) for a in items]}), 200

@announcement_bp.post("")
@role_required(*POSTER_ROLES)
def create_announcement():
    data = request.get_json(silent=True) or {}
    user = get_current_user()
    try:
        announcement = AnnouncementModel.create(data, author_id=user["id"])
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"announcement": _serialize(announcement)}), 201

@announcement_bp.delete("/<int:announcement_id>")
@login_required
def delete_announcement(announcement_id):
    user = get_current_user()
    try:
        AnnouncementModel.delete(announcement_id, user_id=user["id"])
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"deleted": True}), 200