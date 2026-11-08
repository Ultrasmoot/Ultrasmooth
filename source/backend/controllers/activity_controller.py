from flask import Blueprint, jsonify, request

from middleware.auth_middleware import role_required
from models.activity_model import ActivityModel, ValidationError
from services.events import ACTIONS

activity_bp = Blueprint("activity", __name__, url_prefix="/api/activity")

# SRS-8 view and filter the log.
VIEWER_ROLES = ("admin", "professor")


def _serialize(row: dict) -> dict:
    return {
        "id": row["id"],
        "created_at": row["created_at"].isoformat(),
        "actor_id": row["actor_id"],
        "actor_name": row["actor_name"],
        "action": row["action"],
        "action_label": ACTIONS.get(row["action"], row["action"]),
        "resource_id": row["resource_id"],
        "summary": row["summary"],
    }


@activity_bp.get("")
@role_required(*VIEWER_ROLES)
def list_activity():
    args = request.args
    try:
        result = ActivityModel.list(
            date_from=args.get("from"), date_to=args.get("to"), user_id=args.get("user"),
            action=args.get("action"), resource_id=args.get("resource"),
            page=args.get("page", 1), per_page=args.get("per_page", 20),
        )
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    result["items"] = [_serialize(r) for r in result["items"]]
    return jsonify(result), 200


# Options for the filter drop-downs
@activity_bp.get("/meta")
@role_required(*VIEWER_ROLES)
def activity_meta():
    return jsonify({
        "actions": [{"value": k, "label": v} for k, v in ACTIONS.items()],
        "users": ActivityModel.users(),
    }), 200
