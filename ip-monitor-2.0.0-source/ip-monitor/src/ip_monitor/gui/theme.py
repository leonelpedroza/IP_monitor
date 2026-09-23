"""Colours, fonts and layout constants shared by the GUI modules."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from typing import Literal

from ip_monitor.models import RowState

# Row background / foreground per aggregated state (kept from 1.x).
ROW_COLORS: dict[RowState, tuple[str, str]] = {
    RowState.UNKNOWN: ("", "black"),
    RowState.UP: ("#E6F5E6", "#1a7f1a"),
    RowState.DOWN: ("#FFEDED", "#b00020"),
    RowState.DEGRADED: ("#FAFAEB", "#c47a00"),
    RowState.PAUSED: ("", "gray"),
}

CIRCLE_OK = "#2ecc40"
CIRCLE_FAIL = "#e53935"
CIRCLE_NONE = "#b0b0b0"

PIE_RING_COLORS = [  # (min success %, colour)
    (100.0, "#1565c0"),
    (65.0, "#6a1b9a"),
    (45.0, "#ef6c00"),
    (15.0, "#8b0000"),
    (1.0, "#f08080"),
    (0.0, "#d50000"),
]
PIE_RING_EMPTY = "#9e9e9e"
PIE_TEXT = "#f9d400"


def pie_ring_color(success_pct: float | None) -> str:
    if success_pct is None:
        return PIE_RING_EMPTY
    for threshold, colour in PIE_RING_COLORS:
        if success_pct >= threshold:
            return colour
    return PIE_RING_EMPTY


@dataclass(frozen=True)
class Column:
    title: str
    min_px: int
    anchor: Literal["w", "center", "e"]


# Column widths are in *96-DPI pixels*; multiply by ``ui_scale`` at runtime.
COLUMNS: list[Column] = [
    Column("", 34, "center"),  # reorder arrows
    Column("Target", 176, "w"),
    Column("Last 10", 214, "center"),
    Column("Status", 104, "center"),
    Column("Current", 68, "center"),
    Column("Min", 68, "center"),
    Column("Max", 68, "center"),
    Column("Avg", 68, "center"),
    Column("Loss", 56, "center"),
    Column("Controls", 290, "w"),
]

MAX_TARGETS = 64
PIE_CHART_MAX = 4


def format_rtt(ms: float | None) -> str:
    """Format an RTT for display.  Sub-millisecond values display as '<1 ms'
    because ICMP-API/ping.exe backends have 1 ms resolution."""
    if ms is None:
        return "-"
    if ms < 1.0:
        return "<1 ms"
    return f"{ms:.1f} ms"


def format_pct(value: float | None) -> str:
    return "-" if value is None else f"{value:.0f}%"


def system_background(widget: tk.Misc) -> str:
    try:
        return widget.cget("background")
    except tk.TclError:
        return "SystemButtonFace"
