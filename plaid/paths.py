"""Shared filesystem paths for Plaid persistence and exports."""

import os


def get_records_dir():
    return os.getenv("RECORDS_DIR", "records")
