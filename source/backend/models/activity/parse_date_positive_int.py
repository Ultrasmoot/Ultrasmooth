# parse_date_positive_int: part of models.activity.model (split so each file stays small). The public names are still imported from models.activity.model.
import datetime
import models.activity.model as _m

def _parse_date(value, name):
    try:
        return datetime.date.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        raise _m.ValidationError(f"{name} must be a date like 2026-10-31.")

def _positive_int(value, name, maximum=None):
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        raise _m.ValidationError(f"{name} must be a number.")
    if number < 1 or (maximum and number > maximum):
        raise _m.ValidationError(f"{name} must be between 1 and {maximum}." if maximum else f"{name} must be 1 or more.")
    return number


def _date_range(column, date_from, date_to):
    """WHERE parts for an optional, inclusive date range on `column`."""
    clauses, params = [], []
    start = _parse_date(date_from, "from") if date_from else None
    end = _parse_date(date_to, "to") if date_to else None
    if start and end and start > end:
        raise _m.ValidationError("'from' must not be after 'to'.")
    if start:
        clauses.append(f"{column} >= %s")
        params.append(datetime.datetime.combine(start, datetime.time.min))
    if end:
        clauses.append(f"{column} < %s")
        params.append(datetime.datetime.combine(end + datetime.timedelta(days=1), datetime.time.min))
    return clauses, params
