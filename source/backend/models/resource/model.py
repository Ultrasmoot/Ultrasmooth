import mysql.connector

from database.db import get_connection
from services.events import service as events

VALID_STATUSES = {"Available", "In Use", "Maintenance"}
REQUIRED_FIELDS = ["name", "type", "category", "location", "owner"]
MAX_FIELD_LENGTHS = {"name": 150, "type": 100, "category": 100, "location": 150, "owner": 150}

# optional resource details
DETAIL_COLUMNS = {"building": "building", "floor": "floor_level", "capacity": "capacity",
                  "features": "features", "usage_notes": "usage_notes"}
DETAIL_TEXT_LIMITS = {"building": 100, "floor": 50, "usage_notes": 1000}
MAX_CAPACITY = 100000
MAX_FEATURES = 15
MAX_FEATURE_LENGTH = 40
MAX_FEATURES_TOTAL = 500


MAINTENANCE_MANAGED_MSG = (
    "The 'Maintenance' status is managed through Maintenance records "
    "(report an issue to enter it, resolve the issue to leave it)."
)


class ValidationError(Exception):
    pass


from models.resource.archive_unarchive import ResourceModelArchiveUnarchive  # noqa: E402
from models.resource.create_clean_text_details import ResourceModelCreateCleanTextDetails  # noqa: E402
from models.resource.clean_capacity_unique_features import ResourceModelCleanCapacityUniqueFeatures  # noqa: E402
from models.resource.clean_features_list import ResourceModelCleanFeaturesList  # noqa: E402
from models.resource.update import ResourceModelUpdate  # noqa: E402


class ResourceModel(ResourceModelArchiveUnarchive, ResourceModelCreateCleanTextDetails, ResourceModelCleanCapacityUniqueFeatures, ResourceModelCleanFeaturesList, ResourceModelUpdate):

    # allowed sort columns to prevent SQL injection
    # status and availability use custom sorting
    SORTABLE_COLUMNS = {
        "name": "name",
        "category": "category",
        "location": "location",
        "status": "FIELD(status, 'Available', 'In Use', 'Maintenance')",
        "availability": "CASE WHEN status = 'Available' THEN 0 ELSE 1 END",
    }
    DEFAULT_SORT = "status"

    @staticmethod
    def _next_resource_code(conn):
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM resources")
        count = cur.fetchone()[0]
        return f"RES-{count + 1:04d}"

    @staticmethod
    def _validate(data: dict, partial: bool = False):
        """Validate required fields and status."""
        for field in REQUIRED_FIELDS:
            if not partial or field in data:
                value = data.get(field)
                if value is not None and not isinstance(value, str):
                    raise ValidationError(f"'{field}' must be text.")
                if not (value or "").strip():
                    raise ValidationError(f"'{field}' is required.")
                if len(value.strip()) > MAX_FIELD_LENGTHS[field]:
                    raise ValidationError(
                        f"'{field}' must be at most {MAX_FIELD_LENGTHS[field]} characters."
                    )

        status = data.get("status")
        if status is not None and (not isinstance(status, str) or status not in VALID_STATUSES):
            raise ValidationError(f"Status must be one of: {', '.join(sorted(VALID_STATUSES))}.")