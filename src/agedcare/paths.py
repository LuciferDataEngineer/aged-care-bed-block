"""Repository paths."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "data" / "snapshot"
GOLD = ROOT / "data" / "gold"
GEO = ROOT / "data" / "geo"
LAKE = ROOT / "data" / "lakehouse"
DOCS = ROOT / "docs"
SITE = ROOT / "site"
CONTRACTS = ROOT / "data" / "contracts"
LINEAGE_DIR = DOCS / "lineage"
