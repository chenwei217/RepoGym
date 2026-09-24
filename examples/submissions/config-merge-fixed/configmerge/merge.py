from copy import deepcopy
from typing import Any


def merge_config(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge override into base without retaining mutable input objects."""
    result = deepcopy(base)
    for key, value in override.items():
        if value is None:
            result.pop(key, None)
            continue
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_config(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result
