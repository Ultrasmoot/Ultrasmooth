# check-in / check-out history (admin only)
from flask import Blueprint, jsonify, request

from middleware.auth_middleware import role_required
from models.history.model import HistoryModel, ValidationError

history_bp = Blueprint("history", __name__, url_prefix="/api/history")


def _serialize(row: dict) -> dict:
    return {
        "id": row["id"],
        "resource_id": row["resource_id"],
        "resource_name": row["resource_name"],
        "resource_code": row["resource_code"],
        "user_id": row["requester_id"],
        "user_name": row["user_name"],
        "purpose": row["purpose"],
        "start_time": row["start_time"].isoformat(),
        "end_time": row["end_time"].isoformat(),
        "checked_in_at": row["checked_in_at"].isoformat(),
        "checked_out_at": row["checked_out_at"].isoformat() if row["checked_out_at"] else None,
        "status": "Done" if row["checked_out_at"] else "In use",
    }


@history_bp.get("")
@role_required("admin")
def list_history():
    args = request.args
    try:
        result = HistoryModel.list(
            date_from=args.get("from"), date_to=args.get("to"), user_id=args.get("user"),
            resource_id=args.get("resource"), page=args.get("page", 1), per_page=args.get("per_page", 20),
        )
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    result["items"] = [_serialize(r) for r in result["items"]]
    return jsonify(result), 200


@history_bp.get("/meta")
@role_required("admin")
def history_meta():
    return jsonify(HistoryModel.options()), 200
