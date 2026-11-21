import datetime

from database.db import get_connection

MAX_PERIOD_DAYS = 366
DEFAULT_DAYS = 30


class ValidationError(Exception):
    pass


from models.dashboard.summary_load import DashboardModelSummaryLoad  # noqa: E402
from models.dashboard.tally_bookings_utilization import _now, DashboardModelTallyBookingsUtilization  # noqa: E402


class DashboardModel(DashboardModelSummaryLoad, DashboardModelTallyBookingsUtilization):
    pass


def resolve_period(days=None, date_from=None, date_to=None, now=None):
    """The selectable time period: the last N days, or a custom from-to (both days inclusive).
    Returns (start, end) as datetimes with start < end."""
    now = now or _now()
    if date_from or date_to:
        if not (date_from and date_to):
            raise ValidationError("Give both 'from' and 'to' for a custom period.")
        try:
            start_day = datetime.date.fromisoformat(str(date_from).strip())
            end_day = datetime.date.fromisoformat(str(date_to).strip())
        except ValueError:
            raise ValidationError("'from' and 'to' must be dates like 2026-10-31.")
        if start_day > end_day:
            raise ValidationError("'from' must not be after 'to'.")
        start = datetime.datetime.combine(start_day, datetime.time.min)
        end = datetime.datetime.combine(end_day + datetime.timedelta(days=1), datetime.time.min)
    else:
        try:
            n = int(days if days not in (None, "") else DEFAULT_DAYS)
        except (TypeError, ValueError, OverflowError):
            raise ValidationError("days must be a number.")
        if n < 1:
            raise ValidationError("days must be 1 or more.")
        start, end = now - datetime.timedelta(days=n), now
    if (end - start).days > MAX_PERIOD_DAYS:
        raise ValidationError(f"The period can be at most {MAX_PERIOD_DAYS} days.")
    return start, end
