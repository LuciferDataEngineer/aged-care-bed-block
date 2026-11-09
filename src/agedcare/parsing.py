"""Parsers for the committed GEN and ABS snapshots.

Every figure the dashboard shows is derived from these files. The parsers do
not impute missing place counts as zero when the source cell is blank or a dash.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl import load_workbook

from agedcare.common import canon_state, to_float, to_int
from agedcare.paths import SNAPSHOT

GEN = SNAPSHOT / "gen"
ABS = SNAPSHOT / "abs"

SERVICE_LISTS = {
    2021: GEN / "service_list_2021_australia.xlsx",
    2022: GEN / "service_list_2022_australia.xlsx",
    2023: GEN / "service_list_2023_australia.xlsx",
    2024: GEN / "service_list_2024_australia.xlsx",
    2025: GEN / "service_list_2025_australia.xlsx",
}

CURF_FILES = [
    GEN / "curf_2008_2018.csv",
    GEN / "curf_2019.csv",
    GEN / "curf_2020.csv",
    GEN / "curf_2021.csv",
    GEN / "curf_2022.csv",
    GEN / "curf_2023.csv",
    GEN / "curf_2024.xlsx",
    GEN / "curf_2025.xlsx",
]


def _header_map(cells: list[Any]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for index, cell in enumerate(cells):
        key = re.sub(r"\s+", " ", str(cell or "").strip().lower())
        if key and key not in mapping:
            mapping[key] = index
    return mapping


def _cell(row: tuple[Any, ...], mapping: dict[str, int], *names: str) -> Any:
    for name in names:
        if name in mapping and mapping[name] < len(row):
            return row[mapping[name]]
    return None


def load_service_list(path: Path, year: int) -> pd.DataFrame:
    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    workbook.close()
    header_at = None
    mapping: dict[str, int] = {}
    for index, row in enumerate(rows[:20]):
        mapping = _header_map(list(row))
        if "service name" in mapping and "care type" in mapping:
            header_at = index
            break
    if header_at is None:
        raise ValueError(f"No service-list header in {path}")

    records: list[dict[str, Any]] = []
    for row in rows[header_at + 1 :]:
        if row is None:
            continue
        name = _cell(row, mapping, "service name")
        if name is None or not str(name).strip():
            continue
        address_1 = _cell(row, mapping, "physical address", "physical address line 1")
        address_2 = _cell(row, mapping, "physical address line 2")
        address = " ".join(
            part.strip()
            for part in (str(address_1 or ""), str(address_2 or ""))
            if part and str(part).strip()
        )
        state = canon_state(_cell(row, mapping, "physical state", "physical address state"))
        records.append(
            {
                "year": year,
                "service_name": str(name).strip(),
                "address": address,
                "suburb": str(
                    _cell(
                        row,
                        mapping,
                        "physical suburb",
                        "suburb",
                        "physical address suburb",
                    )
                    or ""
                ).strip(),
                "state_code": state,
                "postcode": str(
                    _cell(
                        row,
                        mapping,
                        "physical post code",
                        "postal code",
                        "physical address post code",
                    )
                    or ""
                ).strip(),
                "acpr_name": str(
                    _cell(
                        row,
                        mapping,
                        "2018 aged care planning region (acpr)",
                        "2019 aged care planning region (acpr)",
                    )
                    or ""
                ).strip(),
                "care_type": str(_cell(row, mapping, "care type") or "").strip(),
                "residential_places": to_int(_cell(row, mapping, "residential places")),
                "home_care_places": to_int(_cell(row, mapping, "home care places")),
                "restorative_places": to_int(_cell(row, mapping, "restorative care places")),
                "provider_name": str(_cell(row, mapping, "provider name") or "").strip(),
                "organisation_type": str(_cell(row, mapping, "organisation type") or "").strip(),
                "remoteness": str(_cell(row, mapping, "abs remoteness") or "").strip(),
                "latitude": to_float(_cell(row, mapping, "latitude")),
                "longitude": to_float(_cell(row, mapping, "longitude")),
            }
        )
    frame = pd.DataFrame.from_records(records)
    frame = frame[frame["state_code"].notna()].copy()
    return frame


def load_all_service_lists() -> pd.DataFrame:
    frames = [load_service_list(path, year) for year, path in sorted(SERVICE_LISTS.items())]
    return pd.concat(frames, ignore_index=True)


def load_stocktake_acpr(path: Path | None = None) -> pd.DataFrame:
    """Operational places and the Department's published ratios by ACPR, 30 June 2025."""
    path = path or (GEN / "stocktake_acpr_places_2025.xlsx")
    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    workbook.close()
    records = []
    state = None
    for row in rows:
        if not row or row[1] is None:
            continue
        raw_state = str(row[0]).strip() if row[0] not in (None, "") else ""
        region = str(row[1]).strip()
        if raw_state:
            state = canon_state(raw_state)
        if state is None or state == "AUS":
            continue
        # A blank state cell whose region is the state abbreviation is the state total.
        if not raw_state and canon_state(region) == state:
            continue
        places = to_int(row[2])
        ratio = to_float(row[7]) if len(row) > 7 else None
        if places is None or ratio is None:
            continue
        records.append(
            {
                "year": 2025,
                "state_code": state,
                "acpr_name": region,
                "operational_residential_places": places,
                "home_care_flexible_places": to_int(row[3]),
                "restorative_places": to_int(row[5]) if len(row) > 5 else None,
                "published_ratio_per_1000_70": ratio,
            }
        )
    return pd.DataFrame.from_records(records)


def load_stocktake_state_series(path: Path | None = None) -> pd.DataFrame:
    """Allocated and operational residential places and ratios by state, 2015–2025."""
    path = path or (GEN / "stocktake_comparison_2015_2025.xlsx")
    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    workbook.close()
    records = []
    year = None
    for row in rows:
        if not row or row[0] is None:
            continue
        label = str(row[0]).strip()
        match = re.search(r"As at 30 June (\d{4})", label)
        if match:
            year = int(match.group(1))
            continue
        state = canon_state(label)
        if year is None or state is None:
            continue
        if to_int(row[1]) is None or len(row) < 11:
            continue
        records.append(
            {
                "year": year,
                "state_code": state,
                "allocated_residential_places": to_int(row[1]),
                "allocated_residential_ratio": to_float(row[2]),
                "operational_residential_places": to_int(row[9]),
                "published_ratio_per_1000_70": to_float(row[10]),
                "operational_home_care_flexible_places": to_int(row[11]) if len(row) > 11 else None,
                "operational_restorative_places": to_int(row[15]) if len(row) > 15 else None,
            }
        )
    frame = pd.DataFrame.from_records(records)
    if frame.empty:
        raise ValueError(f"No state stocktake rows parsed from {path}")
    return frame


def _read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        last_error: Exception | None = None
        for encoding in ("utf-8-sig", "utf-8", "latin1"):
            try:
                return pd.read_csv(path, encoding=encoding, low_memory=False)
            except UnicodeDecodeError as exc:
                last_error = exc
        raise RuntimeError(f"Could not decode {path}: {last_error}")
    return pd.read_excel(path, sheet_name=0)


def _pick(frame: pd.DataFrame, *options: str) -> str:
    lookup = {column.lower(): column for column in frame.columns}
    for option in options:
        if option.lower() in lookup:
            return lookup[option.lower()]
    raise KeyError(f"None of {options} in {list(frame.columns)}")


def load_curf_residential() -> pd.DataFrame:
    """Confidentialised service rows for residential care, with operational places.

    These rows are not a service registry: GEN strips the service identifier.
    Places are used only as a cross-check on the stocktake totals.
    """
    frames = []
    for path in CURF_FILES:
        frame = _read_table(path)
        frame.columns = [str(column).strip() for column in frame.columns]
        year_col = _pick(frame, "YEAR")
        state_col = _pick(frame, "STATE")
        program_col = _pick(frame, "PROGRAM_TYPE")
        places_col = _pick(frame, "OPERATIONAL_PLACES")
        acpr_name = None
        acpr_code = None
        for candidate in ("ACPR_NAME_2018", "ACPR_NAME"):
            if candidate in frame.columns:
                acpr_name = candidate
                break
        for candidate in ("ACPR_CODE_2018", "ACPR_CODE"):
            if candidate in frame.columns:
                acpr_code = candidate
                break
        subset = pd.DataFrame(
            {
                "year": pd.to_numeric(frame[year_col], errors="coerce"),
                "state_code": frame[state_col].map(canon_state),
                "acpr_name": frame[acpr_name] if acpr_name else None,
                "acpr_code": frame[acpr_code] if acpr_code else None,
                "program_type": frame[program_col].astype(str),
                "operational_places": pd.to_numeric(
                    frame[places_col].replace({"-": None, "–": None, "—": None}),
                    errors="coerce",
                ),
                "source_file": path.name,
            }
        )
        residential = subset[
            subset["program_type"].str.contains("residential", case=False, na=False)
        ].copy()
        frames.append(residential)
    out = pd.concat(frames, ignore_index=True)
    out = out.dropna(subset=["year", "state_code"])
    out["year"] = out["year"].astype(int)
    return out


def load_erp_june() -> pd.DataFrame:
    """ABS estimated resident population, persons, single year of age, 30 June."""
    frame = pd.read_csv(ABS / "erp_q_age70plus_2014_2026.csv")
    frame = frame[frame["TIME_PERIOD"].astype(str).str.endswith("Q2")].copy()
    frame["year"] = frame["TIME_PERIOD"].str.slice(0, 4).astype(int)
    frame["state_code"] = frame["REGION"].astype(str).map(
        {"AUS": "AUS", "1": "NSW", "2": "VIC", "3": "QLD", "4": "SA", "5": "WA", "6": "TAS", "7": "NT", "8": "ACT"}
    )
    frame["age"] = frame["AGE"].astype(str)
    frame["persons"] = pd.to_numeric(frame["OBS_VALUE"], errors="coerce")
    frame = frame.dropna(subset=["state_code", "persons"])
    return frame[["year", "state_code", "age", "persons"]]


def _projection_age(token: str) -> int | None:
    token = token.strip().lower()
    if token.endswith("and over"):
        # Open age interval. 100 and over is the top code in these tables.
        digits = re.match(r"(\d+)", token)
        return int(digits.group(1)) if digits else None
    if token.isdigit():
        return int(token)
    return None


def load_population_projections() -> pd.DataFrame:
    """ABS Population Projections, series 29 (medium / series B), persons, 30 June.

    State and territory tables are the published Table B1–B8 workbooks.
    Australia is Table B9. The Data API dataflow POP_PROJ returned Australia
    only (state keys 404), so the state series is taken from these spreadsheets
    on the same release.
    """
    folder = ABS / "proj"
    files = {
        "NSW": folder / "3222_Table_B1.xlsx",
        "VIC": folder / "3222_Table_B2.xlsx",
        "QLD": folder / "3222_Table_B3.xlsx",
        "SA": folder / "3222_Table_B4.xlsx",
        "WA": folder / "3222_Table_B5.xlsx",
        "TAS": folder / "3222_Table_B6.xlsx",
        "NT": folder / "3222_Table_B7.xlsx",
        "ACT": folder / "3222_Table_B8.xlsx",
        "AUS": folder / "3222_Table_B9.xlsx",
    }
    records: list[dict[str, Any]] = []
    for state_code, path in files.items():
        workbook = load_workbook(path, read_only=True, data_only=True)
        descriptions: dict[str, str] = {}
        for row in workbook["Index"].iter_rows(values_only=True):
            if row[0] and row[4]:
                descriptions[str(row[4]).strip()] = str(row[0])
        for sheet_name in ("Data1", "Data2"):
            if sheet_name not in workbook.sheetnames:
                continue
            sheet = workbook[sheet_name]
            grid = list(sheet.iter_rows(values_only=True))
            if len(grid) < 11:
                continue
            series_ids = [str(value).strip() if value else "" for value in grid[9]]
            for column, series_id in enumerate(series_ids):
                if column == 0 or not series_id or series_id not in descriptions:
                    continue
                parts = [part.strip() for part in descriptions[series_id].split(";") if part.strip()]
                if "Persons" not in parts:
                    continue
                if not any("29(B)" in part or part == "Series 29(B)" for part in parts):
                    continue
                age = None
                for part in parts:
                    parsed = _projection_age(part)
                    if parsed is not None and part.lower() not in {"series 29(b)"}:
                        # Prefer the age token, which is a bare number or "100 and over".
                        if part[:1].isdigit():
                            age = parsed
                            break
                if age is None or age < 70:
                    continue
                for data_row in grid[10:]:
                    if not data_row or data_row[0] is None or column >= len(data_row):
                        continue
                    when = data_row[0]
                    year = when.year if hasattr(when, "year") else int(str(when)[:4])
                    if year < 2022 or year > 2031:
                        continue
                    persons = to_float(data_row[column])
                    if persons is None:
                        continue
                    records.append(
                        {
                            "year": year,
                            "state_code": state_code,
                            "age": age,
                            "persons": persons,
                            "series": "29(B) medium",
                        }
                    )
        workbook.close()
    return pd.DataFrame.from_records(records)
