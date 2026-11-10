"""Simplify the 2018 Aged Care Planning Region boundaries for an inline SVG map."""

from __future__ import annotations

import json
from pathlib import Path

from shapely.geometry import mapping, shape

from agedcare.common import norm_region
from agedcare.paths import GEO, SNAPSHOT


def _round_coords(value, places: int = 3):
    if isinstance(value, (int, float)):
        return round(float(value), places)
    return [_round_coords(item, places) for item in value]


def simplify_acpr(tolerance: float = 0.02, source: Path | None = None, dest: Path | None = None) -> Path:
    source = source or (SNAPSHOT / "geo" / "acpr_2018.geojson")
    dest = dest or (GEO / "acpr_2018_simplified.geojson")
    raw = json.loads(source.read_text())
    features = []
    for feature in raw["features"]:
        geometry = shape(feature["geometry"])
        if not geometry.is_valid:
            geometry = geometry.buffer(0)
        geometry = geometry.simplify(tolerance, preserve_topology=True)
        props = feature.get("properties") or {}
        mapped = mapping(geometry)
        mapped["coordinates"] = _round_coords(mapped["coordinates"])
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "state_code": str(props.get("state_terr") or "").strip(),
                    "acpr_code": props.get("acpr_code"),
                    "acpr_name": str(props.get("acpr_name") or "").strip(),
                    "join_key": (
                        str(props.get("state_terr") or "").strip()
                        + "|"
                        + norm_region(props.get("acpr_name"))
                    ),
                },
                "geometry": mapped,
            }
        )
    payload = {"type": "FeatureCollection", "features": features}
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, separators=(",", ":")))
    return dest
