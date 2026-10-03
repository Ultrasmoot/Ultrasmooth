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