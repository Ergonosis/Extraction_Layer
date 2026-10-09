"""Load plaid/extractors without clashing with the PyPI ``plaid`` package."""

from __future__ import annotations

import importlib.util
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable


_PLAID_DIR = Path(__file__).resolve().parents[2] / "plaid"
_EXT_PATH = _PLAID_DIR / "extractors" / "plaid_ext.py"


@lru_cache(maxsize=1)
def load_fetch_and_store() -> Callable[..., Any]:
    """Import ``fetch_and_store`` from the legacy extractor module by path.

    Puts ``plaid/`` on ``sys.path`` so ``extractors.*`` and ``paths`` resolve,
    while still loading ``plaid_ext`` under a unique module name so it does not
    register as the top-level ``plaid`` package (PyPI SDK).
    """
    if not _EXT_PATH.is_file():
        raise RuntimeError(f"Plaid extractor not found at {_EXT_PATH}")

    plaid_dir = str(_PLAID_DIR)
    if plaid_dir not in sys.path:
        sys.path.insert(0, plaid_dir)

    spec = importlib.util.spec_from_file_location("portal_plaid_ext", _EXT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load Plaid extractor module")
    module = importlib.util.module_from_spec(spec)
    # Ensure subsequent ``import extractors…`` inside plaid_ext see plaid/.
    sys.modules["portal_plaid_ext"] = module
    spec.loader.exec_module(module)
    fn = getattr(module, "fetch_and_store", None)
    if not callable(fn):
        raise RuntimeError("plaid_ext.fetch_and_store is missing")
    return fn
