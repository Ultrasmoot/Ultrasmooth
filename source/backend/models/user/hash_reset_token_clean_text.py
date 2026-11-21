import hashlib
import re
import models.user.model as _m

def _hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def _clean_text(value, field: str, required: bool = False):
    if value is None or value == "":
        if required:
            raise _m.ValidationError(f"{field} is required.")
        return None
    if not isinstance(value, str):
        raise _m.ValidationError(f"{field} must be text.")
    value = value.strip()
    if required and not value:
        raise _m.ValidationError(f"{field} is required.")
    if len(value) > _m.MAX_TEXT_LENGTH:
        raise _m.ValidationError(f"{field} must be at most {_m.MAX_TEXT_LENGTH} characters.")
    return value or None

def _clean_year(role, value):
    if role != "undergrad_student":
        return None
    if isinstance(value, bool) or value is None or value == "":
        raise _m.ValidationError("Year is required for undergraduate students.")
    if isinstance(value, str):
        value = value.strip()
        if not re.fullmatch(r"\d{1,2}", value):
            raise _m.ValidationError(f"Year must be a number from {_m.MIN_YEAR} to {_m.MAX_YEAR}.")
        value = int(value)
    if not isinstance(value, int) or not _m.MIN_YEAR <= value <= _m.MAX_YEAR:
        raise _m.ValidationError(f"Year must be a number from {_m.MIN_YEAR} to {_m.MAX_YEAR}.")
    return value
