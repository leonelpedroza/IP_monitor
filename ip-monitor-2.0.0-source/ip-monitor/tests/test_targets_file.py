import json

import pytest

from ip_monitor.targets_file import SavedTarget, TargetsFileError, load_targets, parse_targets_json, save_targets


def test_round_trip(tmp_path):
    p = tmp_path / "t.json"
    items = [SavedTarget("10.0.0.1", True, False), SavedTarget("example.com", False, True)]
    save_targets(p, items)
    loaded, skipped = load_targets(p)
    assert loaded == items and skipped == 0
    assert json.loads(p.read_text(encoding="utf-8"))["version"] == 2


def test_legacy_string_list():
    loaded, skipped = parse_targets_json('["10.0.0.1", "Example.COM"]')
    assert [t.address for t in loaded] == ["10.0.0.1", "example.com"] and skipped == 0


def test_legacy_dict_list_with_notifications():
    loaded, _ = parse_targets_json('[{"ip": "10.0.0.1", "notifications": true}]')
    assert loaded == [SavedTarget("10.0.0.1", True, False)]


def test_invalid_and_duplicate_entries_are_skipped_not_fatal():
    loaded, skipped = parse_targets_json('["10.0.0.1", "999.1.1.1", 42, "10.0.0.1", {"address": "http://x"}]')
    assert [t.address for t in loaded] == ["10.0.0.1"] and skipped == 4


@pytest.mark.parametrize("text", ["{not json", '{"targets": "x"}', "42", '{"nope": []}'])
def test_unparseable_files_raise(text):
    with pytest.raises(TargetsFileError):
        parse_targets_json(text)
