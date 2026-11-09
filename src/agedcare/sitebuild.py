"""Copy the stakeholder pages and the gold figures into site/."""

from __future__ import annotations

import shutil
from pathlib import Path

from agedcare.paths import GEO, GOLD, ROOT, SITE

DASHBOARD = ROOT / "dashboard"


def build_site() -> Path:
    if SITE.exists():
        shutil.rmtree(SITE)
    shutil.copytree(DASHBOARD, SITE)
    data = SITE / "data"
    data.mkdir()
    shutil.copy(GOLD / "marts.json", data / "marts.json")
    shutil.copy(GEO / "acpr_2018_simplified.geojson", data / "acpr.geojson")
    return SITE


def main() -> None:
    path = build_site()
    print(f"site written to {path}")


if __name__ == "__main__":
    main()
