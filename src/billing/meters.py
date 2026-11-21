"""Chargeable usage meter names for v1."""

from __future__ import annotations

from enum import StrEnum


class Meter(StrEnum):
    """Meters Ergonosis can bill for (extensible later)."""

    EXPORTS = 'exports'
    API_CALLS = 'api_calls'
