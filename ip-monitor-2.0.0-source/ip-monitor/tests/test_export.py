import csv

from ip_monitor.export import EXPORT_HEADER, default_export_name, export_statistics, statistics_rows
from ip_monitor.models import Target
from ip_monitor.validation import TargetKind
from tests.conftest import ok, timeout


def _target():
    t = Target("10.0.0.1", TargetKind.IPV4)
    t.stats.record(ok(10.0))
    t.stats.record(timeout())
    t.stats.record(ok(20.0))
    return t


def test_rows_reflect_documented_definitions():
    row = statistics_rows([_target()])[0]
    assert row[0] == "10.0.0.1"
    assert row[3:7] == ["3", "2", "1", "33.3"]
    assert row[7:11] == ["10.0", "20.0", "15.0", "20.0"]


def test_export_file_is_utf8_bom_csv(tmp_path):
    path = tmp_path / "out" / "stats.csv"
    export_statistics(path, [_target()])
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(path.open(encoding="utf-8-sig", newline="")))
    assert rows[0] == EXPORT_HEADER and len(rows) == 2


def test_paused_target_status_and_empty_stats():
    t = Target("host.example", TargetKind.HOSTNAME, paused=True)
    row = statistics_rows([t])[0]
    assert row[2] == "Paused" and row[6] == "" and row[7] == ""


def test_default_name_has_timestamp():
    assert default_export_name().startswith("ip_stats_") and default_export_name().endswith(".csv")
