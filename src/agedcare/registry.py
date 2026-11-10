"""Stable service identities and the year-to-year registry diff.

The GEN service lists do not publish a persistent service number in the
national workbook. Identity is the normalised state, care type, service name
and suburb. When that key is not unique inside a single year, the address is
added so two homes on the same row do not collapse.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from agedcare.common import norm_text, sha_id


def _places(value: object) -> int:
    if value is None:
        return 0
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    if math.isnan(number):
        return 0
    return int(round(number))


@dataclass(frozen=True)
class RegistryDiff:
    inserts: list[str]
    updates: list[str]
    deletes: list[str]


def assign_service_ids(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    keys = [
        (
            row.state_code,
            norm_text(row.care_type),
            norm_text(row.service_name),
            norm_text(row.suburb),
        )
        for row in out.itertuples(index=False)
    ]
    out["_key"] = keys
    counts = out.groupby(["year", "_key"], sort=False).size()
    duplicate_keys = set(counts[counts > 1].index)
    ids: list[str] = []
    providers: list[str] = []
    seen: dict[tuple, int] = {}
    for row, key in zip(out.itertuples(index=False), keys, strict=True):
        base = sha_id(*key, row.address, row.postcode) if (row.year, key) in duplicate_keys else sha_id(*key)
        bucket = (row.year, base)
        seen[bucket] = seen.get(bucket, 0) + 1
        if seen[bucket] > 1:
            base = sha_id(base, seen[bucket])
        ids.append(base)
        providers.append(sha_id(row.provider_name) if str(row.provider_name).strip() else sha_id("unknown"))
    out["service_id"] = ids
    out["provider_id"] = providers
    return out.drop(columns=["_key"])


def _tracked(row: pd.Series) -> tuple:
    # Address text is excluded. The 2024 and 2025 workbooks format that column
    # differently, so a raw compare would mark every matched service as changed.
    return (
        row.provider_id,
        norm_text(row.care_type),
        norm_text(row.acpr_name),
        _places(row.residential_places),
        _places(row.home_care_places),
        _places(row.restorative_places),
    )


def diff_year(previous: pd.DataFrame, incoming: pd.DataFrame) -> RegistryDiff:
    prev = previous.drop_duplicates("service_id").set_index("service_id")
    curr = incoming.drop_duplicates("service_id").set_index("service_id")
    prev_ids = set(prev.index)
    curr_ids = set(curr.index)
    inserts = sorted(curr_ids - prev_ids)
    deletes = sorted(prev_ids - curr_ids)
    updates = []
    for service_id in sorted(prev_ids & curr_ids):
        if _tracked(prev.loc[service_id]) != _tracked(curr.loc[service_id]):
            updates.append(service_id)
    return RegistryDiff(inserts=inserts, updates=updates, deletes=deletes)


def yearly_changes(services: pd.DataFrame) -> list[dict]:
    years = sorted(int(year) for year in services["year"].unique())
    changes = []
    for earlier, later in zip(years, years[1:], strict=False):
        diff = diff_year(
            services[services["year"] == earlier],
            services[services["year"] == later],
        )
        place_changes = 0
        prev = services[services["year"] == earlier].drop_duplicates("service_id").set_index("service_id")
        curr = services[services["year"] == later].drop_duplicates("service_id").set_index("service_id")
        for service_id in diff.updates:
            if _places(prev.loc[service_id].residential_places) != _places(
                curr.loc[service_id].residential_places
            ):
                place_changes += 1
        changes.append(
            {
                "from_year": earlier,
                "to_year": later,
                "services_opened": len(diff.inserts),
                "services_closed": len(diff.deletes),
                "services_updated": len(diff.updates),
                "residential_place_changes": place_changes,
            }
        )
    return changes
