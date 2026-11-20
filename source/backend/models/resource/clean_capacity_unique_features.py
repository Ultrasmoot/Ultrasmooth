# capacity and feature validation
import models.resource.model as _m

class ResourceModelCleanCapacityUniqueFeatures:
    @staticmethod
    def _clean_capacity(value):
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise _m.ValidationError("'capacity' must be a whole number.")
        try:
            number = int(value)
        except ValueError:
            raise _m.ValidationError("'capacity' must be a whole number.")
        if number < 1 or number > _m.MAX_CAPACITY:
            raise _m.ValidationError(f"'capacity' must be between 1 and {_m.MAX_CAPACITY}.")
        return number

    @staticmethod
    def _unique_features(items) -> list:
        cleaned, seen = [], set()
        for item in items:
            if not isinstance(item, str):
                raise _m.ValidationError("'features' must be a list of short texts.")
            item = " ".join(item.split())
            if not item or item.lower() in seen:
                continue
            if "," in item:
                raise _m.ValidationError("A feature cannot contain a comma.")
            if len(item) > _m.MAX_FEATURE_LENGTH:
                raise _m.ValidationError(f"Each feature must be at most {_m.MAX_FEATURE_LENGTH} characters.")
            seen.add(item.lower())
            cleaned.append(item)
        return cleaned