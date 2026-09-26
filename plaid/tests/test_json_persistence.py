"""JSON persistence tests — mock plaid_ext so importing apps does not need live Plaid wiring."""

import json
import sys
from unittest.mock import MagicMock

# Stub Plaid extractor before apps pulls it in
_mock_ext = MagicMock()
_mock_ext.PlaidExtractor.return_value.client = MagicMock()
sys.modules["extractors.plaid_ext"] = _mock_ext

import apps  # noqa: E402


def test_load_json_missing_file_returns_empty_dict(records_dir):
    assert apps._load_json(apps.TOKENS_FILE) == {}


def test_save_and_load_json_roundtrip(records_dir):
    apps._save_json(apps.TOKENS_FILE, {"item-1": "access-abc"})
    assert apps._load_json(apps.TOKENS_FILE) == {"item-1": "access-abc"}


def test_save_json_creates_records_dir(tmp_path, monkeypatch):
    nested = tmp_path / "nested" / "records"
    monkeypatch.setenv("RECORDS_DIR", str(nested))
    assert not nested.exists()

    apps._save_json(apps.ITEMS_FILE, {"x": 1})

    assert nested.exists()
    assert json.loads((nested / apps.ITEMS_FILE).read_text(encoding="utf-8")) == {"x": 1}


def test_save_token_persists_access_token(records_dir):
    apps.save_token("item-1", "token-1")
    apps.save_token("item-2", "token-2")

    assert apps.load_tokens() == {"item-1": "token-1", "item-2": "token-2"}
    assert (records_dir / apps.TOKENS_FILE).exists()


def test_save_token_updates_existing_item(records_dir):
    apps.save_token("item-1", "old")
    apps.save_token("item-1", "new")

    assert apps.load_tokens()["item-1"] == "new"


def test_save_item_metadata_shape_and_load(records_dir):
    apps.save_item_metadata("item-1", "ins_3", "Chase")

    meta = apps.load_item_metadata()
    assert meta["item-1"] == {
        "item_id": "item-1",
        "institution_id": "ins_3",
        "institution_name": "Chase",
    }
    assert (records_dir / apps.ITEMS_FILE).exists()


def test_save_item_metadata_creates_dir_when_missing(tmp_path, monkeypatch):
    """Regression: old save_item_metadata did not call makedirs."""
    fresh = tmp_path / "brand_new_records"
    monkeypatch.setenv("RECORDS_DIR", str(fresh))

    apps.save_item_metadata("item-1", "ins_3", "Chase")

    assert (fresh / apps.ITEMS_FILE).exists()


def test_wrappers_use_filename_constants(records_dir):
    apps.save_token("item-1", "tok")
    apps.save_item_metadata("item-1", "ins_1", "Bank")

    assert (records_dir / apps.TOKENS_FILE).name == "tokens.json"
    assert (records_dir / apps.ITEMS_FILE).name == "items.json"
    assert apps.TOKENS_FILE == "tokens.json"
    assert apps.ITEMS_FILE == "items.json"
