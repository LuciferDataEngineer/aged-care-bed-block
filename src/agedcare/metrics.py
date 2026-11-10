"""Supply-gap measures.

Population denominators are ABS estimated resident population at 30 June,
persons, ages 70 and over (and 80 and over). Operational residential places
are the Department of Health stocktake. ACPR ratios published by the
Department use a customised June 2025 population projection based on the
2017 ERP; that population is recovered as places / (published ratio / 1000)
and is labelled as such. It is not ABS ERP.
"""

from __future__ import annotations

import pandas as pd

from agedcare.common import (
    BENCHMARK_PER_1000,
    STATE_NAMES,
    ratio,
    shortfall,
)


def population_bands_safe(erp: pd.DataFrame) -> pd.DataFrame:
    frame = erp.copy()
    frame["age_num"] = pd.to_numeric(frame["age"], errors="coerce")
    frame = frame.dropna(subset=["age_num"])
    frame["is_70"] = frame["age_num"] >= 70
    frame["is_80"] = frame["age_num"] >= 80
    frame["p70"] = frame["persons"].where(frame["is_70"], 0)
    frame["p80"] = frame["persons"].where(frame["is_80"], 0)
    return (
        frame.groupby(["year", "state_code"], as_index=False)[["p70", "p80"]]
        .sum()
        .rename(columns={"p70": "pop_70_plus", "p80": "pop_80_plus"})
    )


def build_state_supply(stocktake: pd.DataFrame, pop: pd.DataFrame) -> pd.DataFrame:
    merged = stocktake.merge(pop, on=["year", "state_code"], how="left")
    merged["per_1000_70"] = [
        ratio(places, population)
        for places, population in zip(
            merged["operational_residential_places"], merged["pop_70_plus"], strict=True
        )
    ]
    merged["per_1000_80"] = [
        ratio(places, population)
        for places, population in zip(
            merged["operational_residential_places"], merged["pop_80_plus"], strict=True
        )
    ]
    merged["shortfall_vs_78"] = [
        shortfall(places, population)
        for places, population in zip(
            merged["operational_residential_places"], merged["pop_70_plus"], strict=True
        )
    ]
    merged["places_to_reach_78"] = merged["shortfall_vs_78"].clip(lower=0)
    merged = merged.sort_values(["state_code", "year"])
    merged["net_operational_places"] = merged.groupby("state_code")[
        "operational_residential_places"
    ].diff()
    return merged


def build_acpr_supply(acpr: pd.DataFrame, pop_2025: pd.DataFrame) -> pd.DataFrame:
    frame = acpr.copy()
    frame["implied_pop_70"] = frame.apply(
        lambda row: (
            row.operational_residential_places / (row.published_ratio_per_1000_70 / 1000.0)
            if row.published_ratio_per_1000_70 and row.published_ratio_per_1000_70 > 0
            else None
        ),
        axis=1,
    )
    state_pop = pop_2025[pop_2025["year"] == 2025][
        ["state_code", "pop_70_plus", "pop_80_plus"]
    ].rename(columns={"pop_70_plus": "state_pop_70", "pop_80_plus": "state_pop_80"})
    frame = frame.merge(state_pop, on="state_code", how="left")
    frame["state_share_80"] = frame["state_pop_80"] / frame["state_pop_70"]
    frame["estimated_pop_80"] = frame["implied_pop_70"] * frame["state_share_80"]
    frame["per_1000_80_estimated"] = [
        ratio(places, population)
        for places, population in zip(
            frame["operational_residential_places"], frame["estimated_pop_80"], strict=True
        )
    ]
    frame["shortfall_vs_78"] = frame["operational_residential_places"] * (
        BENCHMARK_PER_1000 / frame["published_ratio_per_1000_70"] - 1
    )
    frame["places_to_reach_78"] = frame["shortfall_vs_78"].clip(lower=0)
    return frame


def build_outlook(
    supply: pd.DataFrame,
    projections: pd.DataFrame,
    base_year: int = 2025,
    horizon: int = 2031,
) -> pd.DataFrame:
    """Extra residential places by the horizon if today's stock does not change.

    Population growth uses ABS series 29 (medium). The 2025 starting population
    is ABS ERP, not the projection, so the outlook is anchored to the latest
    estimate. Growth is the ratio of the medium-series population at the
    horizon to the medium-series population in the base year, applied to ERP.
    """
    bands = population_bands_safe(projections)
    base_proj = bands[bands["year"] == base_year][
        ["state_code", "pop_70_plus", "pop_80_plus"]
    ].rename(columns={"pop_70_plus": "proj_70_base", "pop_80_plus": "proj_80_base"})
    future = bands[bands["year"] == horizon][
        ["state_code", "pop_70_plus", "pop_80_plus"]
    ].rename(columns={"pop_70_plus": "proj_70_horizon", "pop_80_plus": "proj_80_horizon"})
    current = supply[supply["year"] == base_year][
        [
            "state_code",
            "operational_residential_places",
            "pop_70_plus",
            "pop_80_plus",
            "per_1000_70",
            "shortfall_vs_78",
        ]
    ].rename(
        columns={
            "operational_residential_places": "places_base",
            "pop_70_plus": "erp_70_base",
            "pop_80_plus": "erp_80_base",
            "per_1000_70": "per_1000_70_base",
            "shortfall_vs_78": "shortfall_78_base",
        }
    )
    merged = current.merge(base_proj, on="state_code", how="left").merge(future, on="state_code", how="left")
    merged["growth_70"] = merged["proj_70_horizon"] / merged["proj_70_base"]
    merged["pop_70_horizon"] = merged["erp_70_base"] * merged["growth_70"]
    merged["pop_80_horizon"] = merged["erp_80_base"] * (
        merged["proj_80_horizon"] / merged["proj_80_base"]
    )
    years = horizon - base_year
    merged["places_to_hold_ratio"] = merged["per_1000_70_base"] * merged["pop_70_horizon"] / 1000.0
    merged["extra_places_to_hold_ratio"] = merged["places_to_hold_ratio"] - merged["places_base"]
    merged["places_to_reach_78_horizon"] = BENCHMARK_PER_1000 * merged["pop_70_horizon"] / 1000.0
    merged["extra_places_to_reach_78"] = merged["places_to_reach_78_horizon"] - merged["places_base"]
    merged["annual_extra_to_hold_ratio"] = merged["extra_places_to_hold_ratio"] / years
    merged["annual_extra_to_reach_78"] = merged["extra_places_to_reach_78"] / years
    merged["horizon_year"] = horizon
    merged["base_year"] = base_year
    merged["years"] = years
    merged["state_name"] = merged["state_code"].map(STATE_NAMES)
    return merged


def acpr_outlook(acpr: pd.DataFrame, outlook: pd.DataFrame, horizon: int = 2031, base_year: int = 2025) -> pd.DataFrame:
    """Project each region with its state's medium-series 70+ growth.

    Assumption: the region's share of its state's 70+ population stays at the
    June 2025 Department figure. Places are frozen at the 2025 stocktake.
    """
    growth = outlook[["state_code", "growth_70", "years"]].copy()
    frame = acpr.merge(growth, on="state_code", how="left")
    frame["pop_70_horizon"] = frame["implied_pop_70"] * frame["growth_70"]
    frame["places_to_hold_ratio"] = frame["published_ratio_per_1000_70"] * frame["pop_70_horizon"] / 1000.0
    frame["extra_places_to_hold_ratio"] = (
        frame["places_to_hold_ratio"] - frame["operational_residential_places"]
    )
    frame["extra_places_to_reach_78"] = (
        BENCHMARK_PER_1000 * frame["pop_70_horizon"] / 1000.0 - frame["operational_residential_places"]
    )
    frame["annual_extra_to_hold_ratio"] = frame["extra_places_to_hold_ratio"] / frame["years"]
    frame["annual_extra_to_reach_78"] = frame["extra_places_to_reach_78"] / frame["years"]
    frame["horizon_year"] = horizon
    frame["base_year"] = base_year
    return frame
