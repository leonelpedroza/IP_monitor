import csv
import threading

from ip_monitor.csvlog import CSV_HEADER, ProbeCsvLogger, format_rtt_for_csv
from ip_monitor.models import ProbeResult, ProbeStatus


def test_header_and_rows(tmp_path):
    logger = ProbeCsvLogger(tmp_path / "log.csv")
    logger.log("10.0.0.1", ProbeResult.success(1.234, "10.0.0.1"))
    logger.log("host.example", ProbeResult.failure(ProbeStatus.DNS_FAILURE, "nope"))
    logger.close()
    rows = list(csv.reader((tmp_path / "log.csv").open(encoding="utf-8", newline="")))
    assert rows[0] == CSV_HEADER
    assert rows[1][1:] == ["10.0.0.1", "10.0.0.1", "success", "1.23"]
    assert rows[2][1:] == ["host.example", "", "dns_failure", ""]


def test_disabled_logger_writes_nothing(tmp_path):
    logger = ProbeCsvLogger(tmp_path / "log.csv", enabled=False)
    logger.log("10.0.0.1", ProbeResult.success(1.0))
    assert not (tmp_path / "log.csv").exists()


def test_concurrent_writers_do_not_interleave(tmp_path):
    logger = ProbeCsvLogger(tmp_path / "log.csv")
    threads = 8
    per_thread = 200

    def writer(n: int) -> None:
        for i in range(per_thread):
            logger.log(f"10.0.{n}.{i}", ProbeResult.success(float(i), f"10.0.{n}.{i}"))

    ts = [threading.Thread(target=writer, args=(n,)) for n in range(threads)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    logger.close()
    rows = list(csv.reader((tmp_path / "log.csv").open(encoding="utf-8", newline="")))
    assert len(rows) == 1 + threads * per_thread
    for row in rows[1:]:
        assert len(row) == len(CSV_HEADER)
        assert row[1] == row[2]  # target and resolved ip were written together


def test_write_failure_disables_logging(tmp_path):
    logger = ProbeCsvLogger(tmp_path / "log.csv")
    logger.log("10.0.0.1", ProbeResult.success(1.0))
    logger._file.close()  # simulate the OS closing the handle underneath us

    class Broken:
        def writerow(self, _row):
            raise OSError("disk full")

    logger._writer = Broken()
    logger.log("10.0.0.1", ProbeResult.success(1.0))
    assert logger.failed and not logger.enabled and "disk full" in (logger.error or "")
    logger.log("10.0.0.1", ProbeResult.success(1.0))  # must be a silent no-op now


def test_rtt_formatting():
    assert format_rtt_for_csv(None) == ""
    assert format_rtt_for_csv(0.5) == "0.50"
