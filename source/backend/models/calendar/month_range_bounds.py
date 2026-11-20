import datetime
import models.calendar.model as _m

def month_range(value=None, today=None):
    """'2026-11' -> (first day, first day of the next month). Empty means the current month."""
    if value in (None, ""):
        today = today or datetime.date.today()
        first = today.replace(day=1)
    else:
        try:
            first = datetime.datetime.strptime(str(value).strip(), "%Y-%m").date()
        except ValueError:
            raise _m.ValidationError("month must look like 2026-11.")
    if not 2000 <= first.year <= 2100:
        raise _m.ValidationError("month is out of range.")
    nxt = (first.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    return first, nxt

def _bounds(first, nxt):
    return (datetime.datetime.combine(first, datetime.time.min),
            datetime.datetime.combine(nxt, datetime.time.min))
