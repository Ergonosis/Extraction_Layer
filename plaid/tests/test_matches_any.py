from extractors.matching import matches_any


def test_empty_filter_matches_everything():
    assert matches_any(None, "Chase") is True
    assert matches_any("", "Chase") is True
    assert matches_any([], "Chase") is True


def test_whitespace_only_filter_matches_everything():
    assert matches_any("  ", "Chase") is True
    assert matches_any(["", " "], "Chase") is True


def test_case_insensitive_substring_match():
    assert matches_any("chase", "CHASE BANK", "ins_3") is True


def test_no_match_returns_false():
    assert matches_any("wells", "Chase", "ins_3") is False


def test_list_any_needle_hits():
    assert matches_any(["wells", "chase"], "Chase Checking") is True


def test_list_none_hit():
    assert matches_any(["wells", "boa"], "Chase Checking") is False


def test_strip_on_filter_value():
    assert matches_any("  Chase  ", "My Chase Checking") is True


def test_match_on_later_field():
    assert matches_any("ins_3", "Bank", "ins_3", "item-1") is True


def test_match_on_item_id_field():
    assert matches_any("item-99", "", "", "item-99") is True


def test_account_style_fields_via_matches_any():
    """Same field set _account_matches would pass."""
    assert matches_any(
        "Checking",
        "acc_1",
        "Plaid Checking",
        "Plaid Checking",
        "0000",
        "checking",
        "depository",
    ) is True
    assert matches_any(
        "Saving",
        "acc_1",
        "Plaid Checking",
        "Plaid Checking",
        "0000",
        "checking",
        "depository",
    ) is False
