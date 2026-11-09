"""Build the supply-gap marts from the committed snapshot and write gold outputs."""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from agedcare.common import (
    BENCHMARK_PER_1000,
    REPORTED,
    STATE_NAMES,
    clean_json,
    norm_region,
    status_for_ratio,
)
from agedcare.geo import simplify_acpr
from agedcare.lineage import emit_job
from agedcare.metrics import (
    acpr_outlook,
    build_acpr_supply,
    build_outlook,
    build_state_supply,
    population_bands_safe,
)
from agedcare.parsing import (
    load_all_service_lists,
    load_curf_residential,
    load_erp_june,
    load_population_projections,
    load_stocktake_acpr,
    load_stocktake_state_series,
)
from agedcare.paths import GOLD
from agedcare.registry import assign_service_ids, yearly_changes


def _records(frame: pd.DataFrame) -> list[dict]:
    return clean_json(frame.to_dict(orient="records"))


def _fmt_int(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{int(round(value)):,}"


def _fmt_num(value: float | None, digits: int = 1) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{value:,.{digits}f}"


def build() -> dict:
    stocktake = load_stocktake_state_series()
    acpr = load_stocktake_acpr()
    erp = load_erp_june()
    projections = load_population_projections()
    pop = population_bands_safe(erp)
    supply = build_state_supply(stocktake, pop)
    acpr_supply = build_acpr_supply(acpr, pop)
    outlook = build_outlook(supply, projections)
    regions_outlook = acpr_outlook(acpr_supply, outlook)

    services = assign_service_ids(load_all_service_lists())
    changes = yearly_changes(services)
    residential_services = services[
        services["care_type"].str.contains("Residential|Multi-Purpose|Aboriginal", case=False, na=False)
    ]
    residential_changes = yearly_changes(residential_services)
    listed = (
        services.groupby(["year", "state_code"], as_index=False)
        .agg(
            services=("service_id", "nunique"),
            listed_residential_places=("residential_places", "sum"),
        )
        .sort_values(["year", "state_code"])
    )

    curf = load_curf_residential()
    curf_state = (
        curf.groupby(["year", "state_code"], as_index=False)["operational_places"]
        .sum()
        .rename(columns={"operational_places": "curf_residential_places"})
    )

    national = supply[supply["state_code"] == "AUS"].sort_values("year")
    latest = national[national["year"] == 2025].iloc[0]
    year_2015 = national[national["year"] == 2015].iloc[0]
    aus_outlook = outlook[outlook["state_code"] == "AUS"].iloc[0]

    states_latest = supply[(supply["year"] == 2025) & (supply["state_code"] != "AUS")].copy()
    states_latest["state_name"] = states_latest["state_code"].map(STATE_NAMES)
    states_latest = states_latest.sort_values("shortfall_vs_78", ascending=False)

    acpr_ranked = acpr_supply.sort_values("shortfall_vs_78", ascending=False).copy()
    acpr_ranked["join_key"] = acpr_ranked["state_code"] + "|" + acpr_ranked["acpr_name"].map(norm_region)
    acpr_ranked["state_name"] = acpr_ranked["state_code"].map(STATE_NAMES)
    worst = acpr_ranked.iloc[0]
    with_places = acpr_supply[acpr_supply["operational_residential_places"] > 0]
    lowest_ratio = with_places.sort_values("published_ratio_per_1000_70").iloc[0]

    sa = supply[(supply["state_code"] == "SA") & (supply["year"] == 2025)].iloc[0]
    sa_2015 = supply[(supply["state_code"] == "SA") & (supply["year"] == 2015)].iloc[0]

    # Reconciliation: CURF residential sum versus stocktake operational places.
    curf_2025_states = curf_state[(curf_state["year"] == 2025) & (curf_state["state_code"] != "AUS")]
    curf_aus_2025 = (
        float(curf_2025_states["curf_residential_places"].sum()) if not curf_2025_states.empty else None
    )

    listed_2025 = int(services.loc[services["year"] == 2025, "residential_places"].fillna(0).sum())
    listed_aus_services_2025 = int(services.loc[services["year"] == 2025, "service_id"].nunique())

    gap_2015 = float(year_2015["shortfall_vs_78"])
    gap_2025 = float(latest["shortfall_vs_78"])
    net_last = float(latest["net_operational_places"])
    per_1000 = float(latest["per_1000_70"])
    per_1000_2015 = float(year_2015["per_1000_70"])
    published = float(latest["published_ratio_per_1000_70"])

    headline = (
        f"At 30 June 2025 Australia had {_fmt_int(latest['operational_residential_places'])} "
        f"operational residential aged care places. That is {_fmt_num(per_1000)} places for every "
        f"1,000 people aged 70 or over, using the ABS estimated resident population. "
        f"Holding the long-standing planning benchmark of 78 would take another "
        f"{_fmt_int(gap_2025)} places today. The ratio was {_fmt_num(per_1000_2015)} in 2015, "
        f"and the place gap against that benchmark has grown by {_fmt_int(gap_2025 - gap_2015)} places. "
        f"Last year the stocktake shows a net change of {_fmt_int(net_last)} operational places. "
        f"States have said about 10,600 new places a year are needed."
    )

    kpis = [
        {
            "label": "Places for every 1,000 people aged 70+",
            "value": _fmt_num(per_1000),
            "unit": "Australia, 30 June 2025",
            "takeaway": f"The planning benchmark used here is 78. The published Department ratio, on an older population base, is {_fmt_num(published)}.",
            "status": status_for_ratio(per_1000),
        },
        {
            "label": "Places still needed to reach 78 per 1,000",
            "value": _fmt_int(gap_2025),
            "unit": "operational residential places",
            "takeaway": "This is today's gap if the stock of places does not change. It is not a count of people on a waiting list.",
            "status": "red" if gap_2025 > 0 else "green",
        },
        {
            "label": "Net operational places added last year",
            "value": _fmt_int(net_last),
            "unit": "30 June 2024 to 30 June 2025",
            "takeaway": "States, quoted by the ABC, said about 800 beds were added last year and about 10,600 a year are needed. The stocktake is the counted change in operational places.",
            "status": "red" if net_last < 2000 else "amber",
        },
        {
            "label": "Extra places a year to hold today's ratio to 2031",
            "value": _fmt_int(aus_outlook["annual_extra_to_hold_ratio"]),
            "unit": "ABS medium projection, places frozen at 2025",
            "takeaway": f"Reaching 78 per 1,000 by 2031, from today's stock, would take about {_fmt_int(aus_outlook['annual_extra_to_reach_78'])} extra places a year.",
            "status": "red",
        },
        {
            "label": "Largest regional gap against 78 per 1,000",
            "value": f"{worst['acpr_name']}",
            "unit": f"{STATE_NAMES[worst['state_code']]}, {_fmt_int(worst['shortfall_vs_78'])} places",
            "takeaway": f"Its published ratio is {_fmt_num(worst['published_ratio_per_1000_70'])} places per 1,000 people aged 70+. The lowest ratio is {lowest_ratio['acpr_name']} ({STATE_NAMES[lowest_ratio['state_code']]}) at {_fmt_num(lowest_ratio['published_ratio_per_1000_70'])}.",
            "status": "red",
        },
    ]

    geo_path = simplify_acpr()
    geo = json.loads(geo_path.read_text())
    stock_keys = {(row.state_code, norm_region(row.acpr_name)) for row in acpr_supply.itertuples()}
    geo_keys = set()
    for feature in geo["features"]:
        props = feature["properties"]
        geo_keys.add((props["state_code"], norm_region(props["acpr_name"])))
    unmatched_stock = sorted(stock_keys - geo_keys)
    unmatched_geo = sorted(geo_keys - stock_keys)

    generated = datetime.now(ZoneInfo("Australia/Sydney"))
    marts = {
        "generated_at_aedt": generated.strftime("%-d %B %Y, %-I:%M %p AEDT").replace("AM", "am").replace("PM", "pm"),
        "as_of": "30 June 2025",
        "benchmark_per_1000": BENCHMARK_PER_1000,
        "headline": headline,
        "kpis": kpis,
        "reported": REPORTED,
        "national_series": _records(national),
        "state_series": _records(supply[supply["state_code"] != "AUS"]),
        "states_latest": _records(states_latest),
        "acpr": _records(acpr_ranked),
        "outlook": _records(outlook),
        "acpr_outlook": _records(
            regions_outlook.sort_values("extra_places_to_reach_78", ascending=False)
        ),
        "projection_series": _records(population_bands_safe(projections)),
        "service_changes": changes,
        "residential_service_changes": residential_changes,
        "listed_places": _records(listed),
        "reconciliation": {
            "stocktake_operational_residential_australia_2025": int(latest["operational_residential_places"]),
            "curf_residential_places_australia_2025": curf_aus_2025,
            "service_list_residential_places_2025": listed_2025,
            "service_list_services_2025": listed_aus_services_2025,
            "published_department_ratio_2025": published,
            "abs_ratio_2025": per_1000,
            "sa_abs_ratio_2025": float(sa["per_1000_70"]),
            "sa_published_ratio_2025": float(sa["published_ratio_per_1000_70"]),
            "sa_abs_ratio_2015": float(sa_2015["per_1000_70"]),
            "sa_places_2025": int(sa["operational_residential_places"]),
            "unmatched_acpr_names": [list(item) for item in unmatched_stock],
            "unmatched_geo_names": [list(item) for item in unmatched_geo],
            "net_operational_australia": _records(
                national[["year", "operational_residential_places", "net_operational_places", "per_1000_70", "published_ratio_per_1000_70", "shortfall_vs_78", "pop_70_plus", "pop_80_plus"]]
            ),
        },
        "notes": {
            "population": "ABS Estimated Resident Population, persons, 30 June, single year of age 70 to 100 summed. Age 100 is the top code returned by ERP_Q for this extract.",
            "projections": "ABS Population Projections, Australia, 2022 base to 2071, series 29 (medium / series B), persons. State tables B1–B8 and Australia table B9. Growth from the medium series is applied to the 2025 ERP.",
            "places": "Department of Health stocktake of operational residential places, which include flexible residential places in Multi-Purpose Services, the Innovative Pool and the National Aboriginal and Torres Strait Islander Flexible Aged Care Program. These are operational places, not occupied beds and not vacancies.",
            "acpr_population": "Aged Care Planning Regions are not an ABS geography. The 2025 regional population is the Department's own June 2025 projection implied by its published places and ratio (revised projections based on the 2017 ERP). The 80+ figure applies the state's ABS share of people aged 80+ within the 70+ population. The 2031 regional population keeps each region's 2025 share of its state and grows it with the state's ABS medium-series 70+ growth.",
            "benchmark": "78 residential places per 1,000 people aged 70+ is the residential component of the long-standing Commonwealth target provision ratio. It is a planning yardstick. Home care places have been assigned to people rather than services since February 2017 and are not in this residential benchmark.",
            "hospitals": "Hospital waiting figures are quoted from ABC reports of state sources. They are not calculated from the aged care datasets.",
        },
    }

    GOLD.mkdir(parents=True, exist_ok=True)
    # Parquet gold tables for DuckDB and the Spark publish step.
    supply.to_parquet(GOLD / "supply_gap_state.parquet", index=False)
    acpr_ranked.to_parquet(GOLD / "supply_gap_acpr.parquet", index=False)
    outlook.to_parquet(GOLD / "outlook_2031.parquet", index=False)
    services.to_parquet(GOLD / "service_registry.parquet", index=False)
    (GOLD / "marts.json").write_text(json.dumps(clean_json(marts), indent=2))
    _write_insights(marts)
    emit_job(
        name="build_supply_gap_marts",
        inputs=[
            "snapshot/gen/stocktake_comparison_2015_2025.xlsx",
            "snapshot/gen/stocktake_acpr_places_2025.xlsx",
            "snapshot/abs/erp_q_age70plus_2014_2026.csv",
            "snapshot/abs/proj",
            "snapshot/gen/service_list_2021_2025",
        ],
        outputs=[
            "gold/supply_gap_state",
            "gold/supply_gap_acpr",
            "gold/outlook_2031",
            "gold/service_registry",
            "gold/marts.json",
        ],
    )
    return marts


def _write_insights(marts: dict) -> None:
    recon = marts["reconciliation"]
    national = marts["national_series"]
    latest = next(row for row in national if row["year"] == 2025)
    first = next(row for row in national if row["year"] == 2015)
    outlook = next(row for row in marts["outlook"] if row["state_code"] == "AUS")
    worst = marts["acpr"][0]
    lines = [
        "# What the numbers say",
        "",
        marts["headline"],
        "",
        "## National supply",
        "",
        f"- Operational residential places, 30 June 2025: **{_fmt_int(latest['operational_residential_places'])}**.",
        f"- ABS estimated resident population aged 70+: **{_fmt_int(latest['pop_70_plus'])}**. Aged 80+: **{_fmt_int(latest['pop_80_plus'])}**.",
        f"- Places per 1,000 people aged 70+: **{_fmt_num(latest['per_1000_70'])}** (2015: {_fmt_num(first['per_1000_70'])}).",
        f"- Places per 1,000 people aged 80+: **{_fmt_num(latest['per_1000_80'])}**.",
        f"- Department of Health published ratio, 30 June 2025: **{_fmt_num(latest['published_ratio_per_1000_70'])}** per 1,000 aged 70+. That ratio uses a customised population projection based on the 2017 ERP, so it is not the same denominator as the ABS estimate above.",
        f"- Places short of the 78-per-1,000 benchmark, on the ABS population: **{_fmt_int(latest['shortfall_vs_78'])}**.",
        f"- Net change in operational residential places, 2024 to 2025: **{_fmt_int(latest['net_operational_places'])}**.",
        "",
        "## Where the gap is largest",
        "",
        f"The planning region with the most places still needed to reach 78 per 1,000, using the Department's published ratio and the population implied by it, is **{worst['acpr_name']}** ({worst['state_code']}): **{_fmt_int(worst['shortfall_vs_78'])}** places, ratio **{_fmt_num(worst['published_ratio_per_1000_70'])}**.",
        "",
        "State gaps against 78 per 1,000 people aged 70+ at 30 June 2025, ABS population:",
        "",
    ]
    for row in sorted(
        [item for item in marts["states_latest"]],
        key=lambda item: -(item["shortfall_vs_78"] or 0),
    ):
        lines.append(
            f"- {row['state_name']}: {_fmt_num(row['per_1000_70'])} per 1,000 aged 70+, "
            f"{_fmt_int(row['operational_residential_places'])} places, "
            f"shortfall {_fmt_int(row['shortfall_vs_78'])}."
        )
    lines += [
        "",
        "## Pace versus the reported need",
        "",
        "ABC News on 9 November 2026 quoted SA Health Minister Blair Boyer: at least 10,600 additional federal residential places are needed nationally each year over the next two decades, and last year just 800 beds were added. A federal spokesperson told the ABC the government is supporting construction of around 5,000 additional beds a year. Those are reported claims.",
        "",
        f"On the stocktake, operational residential places changed by **{_fmt_int(latest['net_operational_places'])}** between 30 June 2024 and 30 June 2025.",
        "",
        f"Using the ABS medium projection, keeping today's national ratio of {_fmt_num(latest['per_1000_70'])} through to 2031 would require about **{_fmt_int(outlook['extra_places_to_hold_ratio'])}** more places in total if none of today's places close, or about **{_fmt_int(outlook['annual_extra_to_hold_ratio'])}** a year for six years. Reaching 78 per 1,000 by 2031 would require about **{_fmt_int(outlook['extra_places_to_reach_78'])}** more places, about **{_fmt_int(outlook['annual_extra_to_reach_78'])}** a year.",
        "",
        "## Service list, 2021 to 2025",
        "",
        "The annual service lists are the operational registry used for the change-data feed. They are matched on state, care type, service name and suburb because the national workbook does not include a stable service number. Spelling changes (for example a town name) look like a closure plus an opening, so those counts are an upper bound.",
        "",
        "Residential, Multi-Purpose and National Aboriginal and Torres Strait Islander Flexible services:",
        "",
    ]
    for change in marts["residential_service_changes"]:
        lines.append(
            f"- {change['from_year']} to {change['to_year']}: "
            f"{change['services_opened']:,} services appeared, "
            f"{change['services_closed']:,} disappeared, "
            f"{change['residential_place_changes']:,} changed their residential place count, "
            f"{change['services_updated']:,} had some operational field change."
        )
    lines += [
        "",
        f"Listed residential places on the 30 June 2025 service list sum to **{recon['service_list_residential_places_2025']:,}**, across **{recon['service_list_services_2025']:,}** services. The stocktake's operational residential total is **{recon['stocktake_operational_residential_australia_2025']:,}**. Those two totals meet. The confidentialised GEN CURF sums to **{_fmt_int(recon['curf_residential_places_australia_2025'])}** places on rows whose program is residential care. It is lower because the stocktake also counts flexible residential places delivered through Multi-Purpose Services and the National Aboriginal and Torres Strait Islander Flexible Aged Care Program, which the CURF stores under those program names.",
        "",
        "## Assumptions that move the 2031 numbers",
        "",
        "- The projection is ABS series 29, the medium series (series B), not a forecast.",
        "- State 70+ growth is applied to the 2025 ABS ERP. The projection's own 2025 level is used only to measure the growth rate between 2025 and 2031.",
        "- Each Aged Care Planning Region keeps its June 2025 share of its state's 70+ population. Regions that age faster or slower than their state are not separately observed.",
        "- The 80+ ratio for a region applies the state's 80+ share of the 70+ population.",
        "- 'Extra places' assumes the 2025 operational stock stays open. Closures would add to the gap. Places already in the pipeline are not subtracted, because the stocktake's provisional places are not modelled as certain openings.",
        "- 78 per 1,000 is a planning benchmark, not a count of people who need a bed. Some of the people behind the South Australian hospital figure need a place now; the ratio gap is a population-capacity comparison.",
        "",
        "## What this does not measure",
        "",
        "Operational places are not occupied beds, vacancies, or staffed beds. A region can have places on the stocktake and still have no bed free this week. Hospital patients waiting for a place are taken from ABC reports of state figures, not from this dataset. Home care packages are mostly assigned to people rather than services, so they are outside the residential place counts.",
        "",
    ]
    from agedcare.paths import ROOT

    (ROOT / "INSIGHTS.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    marts = build()
    latest = next(row for row in marts["national_series"] if row["year"] == 2025)
    print("Australia 2025 places", latest["operational_residential_places"])
    print("per 1000 70+", round(latest["per_1000_70"], 2), "published", round(latest["published_ratio_per_1000_70"], 2))
    print("pop70", round(latest["pop_70_plus"]), "shortfall", round(latest["shortfall_vs_78"]))
    print("net", latest["net_operational_places"])
    print("ACPR rows", len(marts["acpr"]), "unmatched", marts["reconciliation"]["unmatched_acpr_names"])
    print("geo unmatched", marts["reconciliation"]["unmatched_geo_names"])
    print("changes", marts["service_changes"])
    outlook = next(row for row in marts["outlook"] if row["state_code"] == "AUS")
    print("outlook hold/yr", round(outlook["annual_extra_to_hold_ratio"]), "to78/yr", round(outlook["annual_extra_to_reach_78"]))


if __name__ == "__main__":
    main()
