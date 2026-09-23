"""Save/load target lists (JSON), with backward compatibility.

Format version 2::

    {"version": 2, "targets": [{"address": "10.0.0.1", "sound_notifications": false, "paused": false}]}

Legacy formats produced by IP Monitor 1.x are also accepted:
``["10.0.0.1", "example.com"]`` and ``[{"ip": "...", "notifications": true}]``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ip_monitor.config import atomic_write_text
from ip_monitor.validation import InvalidTargetError, parse_target

FORMAT_VERSION = 2


class TargetsFileError(ValueError):
    """Raised when a targets file cannot be parsed."""


@dataclass(frozen=True)
class SavedTarget:
    address: str
    sound_notifications: bool = False
    paused: bool = False


def _coerce_entry(entry: Any) -> SavedTarget | None:
    if isinstance(entry, str):
        address, sound, paused = entry, False, False
    elif isinstance(entry, dict):
        address = entry.get("address") or entry.get("ip") or ""
        sound = bool(entry.get("sound_notifications", entry.get("notifications", False)))
        paused = bool(entry.get("paused", False))
    else:
        return None
    try:
        parsed = parse_target(str(address))
    except InvalidTargetError:
        return None
    return SavedTarget(parsed.address, sound, paused)


def parse_targets_json(text: str) -> tuple[list[SavedTarget], int]:
    """Return ``(targets, skipped_count)``.  Invalid entries are skipped, not fatal."""
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise TargetsFileError(f"Not a valid JSON targets file: {exc}") from exc

    if isinstance(data, dict):
        entries = data.get("targets")
        if not isinstance(entries, list):
            raise TargetsFileError("Targets file has no 'targets' list.")
    elif isinstance(data, list):
        entries = data
    else:
        raise TargetsFileError("Targets file must contain a list of targets.")

    targets: list[SavedTarget] = []
    skipped = 0
    seen: set[str] = set()
    for entry in entries:
        saved = _coerce_entry(entry)
        if saved is None or saved.address in seen:
            skipped += 1
            continue
        seen.add(saved.address)
        targets.append(saved)
    return targets, skipped


def load_targets(path: Path) -> tuple[list[SavedTarget], int]:
    return parse_targets_json(path.read_text(encoding="utf-8"))


def targets_json_text(targets: list[SavedTarget]) -> str:
    payload = {
        "version": FORMAT_VERSION,
        "targets": [
            {"address": t.address, "sound_notifications": t.sound_notifications, "paused": t.paused} for t in targets
        ],
    }
    return json.dumps(payload, indent=2)


def save_targets(path: Path, targets: list[SavedTarget]) -> None:
    atomic_write_text(path, targets_json_text(targets))
