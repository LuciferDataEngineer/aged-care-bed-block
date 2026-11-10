"""Validate CDC envelopes and gold rows against the YAML contracts."""

from __future__ import annotations

import jsonschema
import yaml

from agedcare.paths import CONTRACTS, GOLD


def load_contract(name: str) -> dict:
    path = CONTRACTS / name
    document = yaml.safe_load(path.read_text())
    jsonschema.Draft202012Validator.check_schema(document["schema"])
    return document


def validate_records(name: str, records: list[dict]) -> None:
    document = load_contract(name)
    validator = jsonschema.Draft202012Validator(document["schema"])
    errors = []
    for index, record in enumerate(records):
        for error in validator.iter_errors(record):
            errors.append(f"{name} row {index}: {error.message}")
            if len(errors) >= 8:
                break
        if len(errors) >= 8:
            break
    if errors:
        raise AssertionError("\n".join(errors))


def validate_gold_state(limit: int | None = None) -> int:
    import pandas as pd

    frame = pd.read_parquet(GOLD / "supply_gap_state.parquet")
    records = frame.to_dict(orient="records")
    # Parquet may restore integers as numpy types. Coerce the contracted fields.
    cleaned = []
    for record in records:
        cleaned.append(
            {
                **record,
                "year": int(record["year"]),
                "state_code": str(record["state_code"]),
                "operational_residential_places": int(record["operational_residential_places"]),
                "pop_70_plus": float(record["pop_70_plus"]),
                "per_1000_70": float(record["per_1000_70"]),
                "shortfall_vs_78": float(record["shortfall_vs_78"]),
            }
        )
    if limit:
        cleaned = cleaned[:limit]
    validate_records("gold_supply_gap_state.schema.yaml", cleaned)
    return len(cleaned)


def main() -> None:
    count = validate_gold_state()
    sample = {
        "op": "c",
        "ts_ms": 1,
        "before": None,
        "after": {"service_id": "abc"},
        "source": {"table": "services", "db": "agedcare", "schema": "registry"},
    }
    validate_records("cdc_envelope.schema.yaml", [sample])
    print(f"contracts ok, gold rows {count}")


if __name__ == "__main__":
    main()
