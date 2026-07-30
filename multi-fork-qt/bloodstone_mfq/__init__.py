"""Bloodstone Multi-Fork Qt Wallet."""

from pathlib import Path

__version__ = (Path(__file__).resolve().parent.parent / "VERSION").read_text(
    encoding="utf-8"
).strip()

APP_NAME = "Bloodstone Multi-Fork Qt Wallet"
APP_ORG = "Bloodstone"
APP_ID = "rocks.bloodstone.multi-fork-qt"
