# -*- coding: utf-8 -*-
"""Shared set-up for the figure templates. You should not need to edit this."""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # write files rather than opening windows, which is reliable under WSL

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

FIGURE_DIR = ROOT / "student_task" / "figures"
FIGURE_DIR.mkdir(parents=True, exist_ok=True)

PHASE_COLOURS = {"El Nino": "#c0392b", "Neutral": "#7f8c8d", "La Nina": "#2471a3"}
STAGE_COLOURS = {"initial": "#d5f5e3", "development": "#abebc6", "mid": "#f9e79f", "late": "#f5cba7"}


def season_label(season: int) -> str:
    """2015 -> '2015/16'."""
    return f"{season}/{(season + 1) % 100:02d}"


def save(fig, name: str) -> Path:
    path = FIGURE_DIR / name
    fig.savefig(path, dpi=200, bbox_inches="tight")
    print(f"Saved {path.relative_to(ROOT)}")
    return path
