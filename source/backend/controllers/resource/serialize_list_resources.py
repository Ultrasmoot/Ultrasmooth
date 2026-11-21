import controllers.resource.controller as _m

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
        "building": r.get("building"),
        "floor": r.get("floor_level"),
        "capacity": r.get("capacity"),
        "features": [f for f in (r.get("features") or "").split(",") if f],
        "usage_notes": r.get("usage_notes"),
    }

@_m.resource_bp.get("")
@_m.login_required
def list_resources():
    """view/search resources. Available to every authenticated role"""
    search = _m.request.args.get("q")
    category = _m.request.args.get("category")
    location = _m.request.args.get("location")
    status = _m.request.args.get("status")
    include_archived = _m.request.args.get("include_archived") == "true"
    sort_by = _m.request.args.get("sort", _m.ResourceModel.DEFAULT_SORT)
    sort_dir = _m.request.args.get("dir", "asc")

    user = _m.get_current_user()
    # Only admins may ever see archived resources.
    if include_archived and user["role"] != "admin":
        include_archived = False

    resources = _m.ResourceModel.list(
        search=search, category=category, location=location,
        status=status, include_archived=include_archived,
        sort_by=sort_by, sort_dir=sort_dir,
    )
    return _m.jsonify({"resources": [_m._serialize(r) for r in resources]}), 200

@_m.resource_bp.get("/<int:resource_id>")
@_m.login_required
def get_resource(resource_id):
    resource = _m.ResourceModel.get(resource_id)
    # Archived resources are hidden from everyone except admins.
    if not resource or (resource["is_archived"] and _m.get_current_user()["role"] != "admin"):
        return _m.jsonify({"error": "Resource not found."}), 404
    return _m.jsonify({"resource": _m._serialize(resource)}), 200


# Everyone gets the description and the booked time slots (without names); admin and
@_m.resource_bp.get("/<int:resource_id>/detail")
@_m.login_required
def resource_detail(resource_id):
    user = _m.get_current_user()
    staff = user["role"] in ("admin", "professor")
    result = _m.ResourceDetailModel.get(resource_id, staff, include_archived=user["role"] == "admin")
    if result is None:
        return _m.jsonify({"error": "Resource not found."}), 404
    result["resource"] = _m._serialize(result["resource"])
    return _m.jsonify(result), 200

@_m.resource_bp.post("")
@_m.role_required("admin")
def create_resource():
    """SRS-2: only Lab Managers/Administrators may add resource records."""
    data = _m.request.get_json(silent=True) or {}
    try:
        resource = _m.ResourceModel.create(data, actor_id=_m.get_current_user()["id"])
    except _m.ValidationError as e:
        return _m.jsonify({"error": str(e)}), 400
    return _m.jsonify({"resource": _m._serialize(resource)}), 201
