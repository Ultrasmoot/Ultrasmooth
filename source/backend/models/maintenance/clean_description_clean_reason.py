import datetime
import models.maintenance.model as _m

class MaintenanceModelCleanDescriptionCleanReason:
    # ---------- validation ----------
    @staticmethod
    def _clean_description(value):
        if value is not None and not isinstance(value, str):
            raise _m.ValidationError("description must be text.")
        description = (value or "").strip()
        if not description:
            raise _m.ValidationError("description is required.")
        if len(description) > _m.MAX_DESCRIPTION_LENGTH:
            raise _m.ValidationError(
                f"description must be at most {_m.MAX_DESCRIPTION_LENGTH} characters "
                f"(currently {len(description)})."
            )
        return description

    @staticmethod
    def _clean_reason(value):
        if value is not None and not isinstance(value, str):
            raise _m.ValidationError("reason must be text.")
        reason = (value or "").strip()
        if not reason:
            raise _m.ValidationError("reason is required when rejecting a report.")
        if len(reason) > _m.MAX_REASON_LENGTH:
            raise _m.ValidationError(
                f"reason must be at most {_m.MAX_REASON_LENGTH} characters (currently {len(reason)})."
            )
        return reason

    @staticmethod
    def _clean_date(value):
        if not value:
            raise _m.ValidationError("date is required.")
        if not isinstance(value, str):
            raise _m.ValidationError("date must be a valid date (YYYY-MM-DD).")
        try:
            parsed = datetime.date.fromisoformat(value.strip()[:10])
        except ValueError:
            raise _m.ValidationError("date must be a valid date (YYYY-MM-DD).")
        # An issue may have been noticed earlier, but it cannot be dated in the future.
        if parsed > datetime.date.today():
            raise _m.ValidationError("date cannot be in the future.")
        return parsed

    @staticmethod
    def _clean_status(value):
        status = value.strip() if isinstance(value, str) else None
        if status not in _m.EDITABLE_STATUSES:
            raise _m.ValidationError("status must be 'Open' or 'In Progress'.")
        return status
