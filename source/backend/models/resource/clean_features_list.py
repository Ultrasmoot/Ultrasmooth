# feature cleaning and resource listing
import models.resource.model as _m

class ResourceModelCleanFeaturesList:
    @staticmethod
    def _clean_features(value):
        if value is None:
            return None
        items = value if isinstance(value, list) else (value.split(",") if isinstance(value, str) else None)
        if items is None:
            raise _m.ValidationError("'features' must be a list of short texts.")
        cleaned = _m.ResourceModel._unique_features(items)
        if len(cleaned) > _m.MAX_FEATURES:
            raise _m.ValidationError(f"At most {_m.MAX_FEATURES} features.")
        joined = ",".join(cleaned)
        if len(joined) > _m.MAX_FEATURES_TOTAL:
            raise _m.ValidationError("The features list is too long.")
        return joined or None

    @staticmethod
    def list(search: str = None, category: str = None, location: str = None,
              status: str = None, include_archived: bool = False,
              sort_by: str = "status", sort_dir: str = "asc"):
        """Search, filter, and sort resources."""
        conn = _m.get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            clauses = []
            params = []

            if not include_archived:
                clauses.append("is_archived = 0")
            if search:
                clauses.append("name LIKE %s")
                params.append(f"%{search}%")
            if category:
                clauses.append("category = %s")
                params.append(category)
            if location:
                clauses.append("location = %s")
                params.append(location)
            if status:
                clauses.append("status = %s")
                params.append(status)

            sql = "SELECT * FROM resources"
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)

            order_expr = _m.ResourceModel.SORTABLE_COLUMNS.get(
                sort_by, _m.ResourceModel.SORTABLE_COLUMNS[_m.ResourceModel.DEFAULT_SORT]
            )
            direction = "DESC" if str(sort_dir).lower() == "desc" else "ASC"
            sql += f" ORDER BY is_archived ASC, {order_expr} {direction}, name ASC, id ASC"

            cur.execute(sql, tuple(params))
            return cur.fetchall()
        finally:
            conn.close()