"""Shared text-filter matching (no third-party imports)."""


def matches_any(filter_value, *fields) -> bool:
    """Return True if any filter word appears in the given fields (or if filter is empty)."""
    if not filter_value:
        return True
    values = filter_value if isinstance(filter_value, list) else [filter_value]
    needles = [str(v).strip().lower() for v in values if str(v).strip()]
    if not needles:
        return True
    haystack = " ".join(str(f) for f in fields).lower()
    return any(needle in haystack for needle in needles)
