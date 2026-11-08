# in-web notifications (the bell)
from flask import Blueprint, jsonify

from middleware.auth_middleware import get_current_user, login_required
from models.notification_model import NotificationModel

notification_bp = Blueprint("notifications", __name__, url_prefix="/api/notifications")


def _serialize(n: dict) -> dict:
    return {
        "id": n["id"],
        "kind": n["kind"],
        "title": n["title"],
        "body": n["body"],
        "view": n["link_view"],
        "is_read": bool(n["is_read"]),
        "created_at": n["created_at"].isoformat(),
    }


# Everyone sees only their own notifications
@notification_bp.get("")
@login_required
def list_notifications():
    uid = get_current_user()["id"]
    items = NotificationModel.list(uid)
    return jsonify({"notifications": [_serialize(n) for n in items],
                    "unread": NotificationModel.unread_count(uid)}), 200


# the page polls this every 30-60 seconds for the red badge
@notification_bp.get("/unread-count")
@login_required
def unread_count():
    return jsonify({"unread": NotificationModel.unread_count(get_current_user()["id"])}), 200


@notification_bp.post("/<int:notification_id>/read")
@login_required
def mark_read(notification_id):
    if not NotificationModel.mark_read(get_current_user()["id"], notification_id):
        return jsonify({"error": "Notification not found."}), 404
    return jsonify({"read": True}), 200


@notification_bp.post("/read-all")
@login_required
def mark_all_read():
    NotificationModel.mark_all_read(get_current_user()["id"])
    return jsonify({"read": True}), 200
