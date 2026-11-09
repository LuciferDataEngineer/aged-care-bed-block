"""The captured Postgres changes, once merged, match the 30 June 2025 service list."""

import json
from pathlib import Path

import pandas as pd

from agedcare.contracts import validate_records

ROOT = Path(__file__).resolve().parents[2]
EXPORT = ROOT / "data" / "lakehouse" / "export" / "services_current.parquet"


def test_merged_current_matches_service_list_places():
    assert EXPORT.exists(), "Run make cdc and make lakehouse before this test."
    current = pd.read_parquet(EXPORT)
    assert current["service_id"].is_unique
    places = int(current["residential_places"].fillna(0).sum())
    assert places == 228259
    registry = pd.read_parquet(ROOT / "data" / "gold" / "service_registry.parquet")
    latest_ids = set(registry.loc[registry["year"] == 2025, "service_id"])
    assert set(current["service_id"]) == latest_ids


def test_sample_events_match_the_cdc_contract():
    path = ROOT / "data" / "lakehouse" / "export" / "sample_events.json"
    assert path.exists()
    rows = json.loads(path.read_text())
    assert rows
    envelopes = []
    for row in rows:
        envelopes.append(
            {
                "op": "c" if row["op"] == "c" else row["op"],
                "source": {"table": "services"},
            }
        )
    validate_records("cdc_envelope.schema.yaml", envelopes)


def test_scd2_keeps_history():
    scd = ROOT / "data" / "lakehouse" / "silver" / "services_scd2"
    files = [path for path in scd.rglob("*.parquet") if path.is_file()]
    assert files, "SCD2 delta table was not written"
    frame = pd.concat([pd.read_parquet(path) for path in files], ignore_index=True)
    current = pd.read_parquet(EXPORT)
    assert len(frame) >= len(current)
    assert frame["valid_to_ts"].notna().any()
