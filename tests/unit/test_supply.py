"""The supply-gap figures have to match the stocktake and the ABS extract."""

import json
from pathlib import Path

import pandas as pd
import pytest

from agedcare.common import shortfall
from agedcare.contracts import validate_gold_state, validate_records
from agedcare.metrics import build_outlook, build_state_supply, population_bands_safe
from agedcare.parsing import load_erp_june, load_population_projections, load_stocktake_state_series
from agedcare.registry import assign_service_ids, diff_year

ROOT = Path(__file__).resolve().parents[2]


def test_shortfall_formula():
    assert shortfall(66, 1000, 78) == pytest.approx(12)
    assert shortfall(80, 1000, 78) == pytest.approx(-2)


def test_australia_2025_stocktake_and_abs_ratio():
    stocktake = load_stocktake_state_series()
    pop = population_bands_safe(load_erp_june())
    supply = build_state_supply(stocktake, pop)
    australia = supply[(supply["state_code"] == "AUS") & (supply["year"] == 2025)].iloc[0]
    assert int(australia["operational_residential_places"]) == 228259
    assert australia["per_1000_70"] == pytest.approx(66.14, abs=0.05)
    assert int(australia["net_operational_places"]) == 794
    assert australia["published_ratio_per_1000_70"] == pytest.approx(66.99, abs=0.02)
    # 2015 was still above the 78 benchmark. 2025 is not.
    earlier = supply[(supply["state_code"] == "AUS") & (supply["year"] == 2015)].iloc[0]
    assert earlier["per_1000_70"] > 78
    assert australia["shortfall_vs_78"] > 40000


def test_state_gaps_sum_close_to_national():
    stocktake = load_stocktake_state_series()
    pop = population_bands_safe(load_erp_june())
    supply = build_state_supply(stocktake, pop)
    latest = supply[supply["year"] == 2025]
    national = float(latest.loc[latest["state_code"] == "AUS", "shortfall_vs_78"].iloc[0])
    states = float(latest.loc[latest["state_code"] != "AUS", "shortfall_vs_78"].sum())
    assert states == pytest.approx(national, rel=0.01)


def test_outlook_hold_is_below_the_reported_10600_and_78_is_above():
    stocktake = load_stocktake_state_series()
    supply = build_state_supply(stocktake, population_bands_safe(load_erp_june()))
    outlook = build_outlook(supply, load_population_projections())
    australia = outlook[outlook["state_code"] == "AUS"].iloc[0]
    assert 7000 < australia["annual_extra_to_hold_ratio"] < 10600
    assert australia["annual_extra_to_reach_78"] > 10600


def test_service_identity_tracks_a_place_change():
    frame = pd.DataFrame(
        [
            {
                "year": 2024,
                "state_code": "SA",
                "care_type": "Residential",
                "service_name": "Example House",
                "suburb": "Adelaide",
                "address": "1 King St",
                "postcode": "5000",
                "provider_name": "Example Care",
                "acpr_name": "Metropolitan East",
                "residential_places": 40,
                "home_care_places": None,
                "restorative_places": None,
            },
            {
                "year": 2025,
                "state_code": "SA",
                "care_type": "Residential",
                "service_name": "Example House",
                "suburb": "Adelaide",
                "address": "1 King Street",
                "postcode": "5000",
                "provider_name": "Example Care",
                "acpr_name": "Metropolitan East",
                "residential_places": 55,
                "home_care_places": None,
                "restorative_places": None,
            },
        ]
    )
    identified = assign_service_ids(frame)
    assert identified["service_id"].nunique() == 1
    diff = diff_year(identified[identified.year == 2024], identified[identified.year == 2025])
    assert diff.inserts == []
    assert diff.deletes == []
    assert len(diff.updates) == 1


def test_gold_contract_and_committed_headline():
    count = validate_gold_state()
    assert count == 11 * 9  # 2015–2025, eight states plus Australia
    marts = json.loads((ROOT / "data" / "gold" / "marts.json").read_text())
    latest = next(row for row in marts["national_series"] if row["year"] == 2025)
    assert latest["operational_residential_places"] == 228259
    assert latest["net_operational_places"] == 794


def test_cdc_contract_fixture():
    envelope = json.loads((ROOT / "tests" / "fixtures" / "cdc_envelope.json").read_text())
    validate_records("cdc_envelope.schema.yaml", [envelope])
