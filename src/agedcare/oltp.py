"""Load the GEN service lists into Postgres and replay each 30 June as changes."""

from __future__ import annotations

import json

import psycopg

from agedcare.lineage import emit_job
from agedcare.parsing import load_all_service_lists
from agedcare.paths import GOLD
from agedcare.registry import assign_service_ids, diff_year
from agedcare.stack import wait_for_streaming

DSN = "postgresql://agedcare:agedcare@localhost:5432/agedcare"


def _number_or_none(value, as_int: bool = False):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return int(round(number)) if as_int else number


def _int_or_none(value) -> int | None:
    return _number_or_none(value, as_int=True)


def _connect():
    return psycopg.connect(DSN, autocommit=False)


def reset_tables(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "TRUNCATE registry.services, registry.places_by_year, registry.providers"
        )
    conn.commit()


def _providers(frame) -> list[tuple]:
    latest = frame.sort_values("year").drop_duplicates("provider_id", keep="last")
    rows = []
    for row in latest.itertuples(index=False):
        rows.append((row.provider_id, row.provider_name or "Unknown", row.organisation_type or None))
    return rows


def _service_tuple(row) -> tuple:
    return (
        row.service_id,
        row.provider_id,
        row.service_name,
        row.care_type,
        row.state_code,
        row.acpr_name or None,
        row.suburb or None,
        row.address or None,
        row.postcode or None,
        _number_or_none(row.latitude),
        _number_or_none(row.longitude),
        _int_or_none(row.residential_places),
        _int_or_none(row.home_care_places),
        _int_or_none(row.restorative_places),
        int(row.year),
    )


def _place_tuple(row) -> tuple:
    return (
        row.service_id,
        int(row.year),
        _int_or_none(row.residential_places),
        _int_or_none(row.home_care_places),
        _int_or_none(row.restorative_places),
        row.state_code,
        row.acpr_name or None,
        row.care_type,
    )


INSERT_SERVICE = """
INSERT INTO registry.services (
    service_id, provider_id, service_name, care_type, state_code, acpr_name,
    suburb, address, postcode, latitude, longitude,
    residential_places, home_care_places, restorative_places, source_year
) VALUES (
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
)
"""

UPDATE_SERVICE = """
UPDATE registry.services SET
    provider_id = %s,
    service_name = %s,
    care_type = %s,
    state_code = %s,
    acpr_name = %s,
    suburb = %s,
    address = %s,
    postcode = %s,
    latitude = %s,
    longitude = %s,
    residential_places = %s,
    home_care_places = %s,
    restorative_places = %s,
    source_year = %s,
    updated_at = now()
WHERE service_id = %s
"""


def replay(conn, services) -> dict:
    years = sorted(int(year) for year in services["year"].unique())
    stats = {
        "provider_inserts": 0,
        "service_inserts": 0,
        "service_updates": 0,
        "service_deletes": 0,
        "place_inserts": 0,
        "years": years,
    }
    with conn.cursor() as cur:
        providers = _providers(services)
        cur.executemany(
            """
            INSERT INTO registry.providers (provider_id, provider_name, organisation_type)
            VALUES (%s, %s, %s)
            ON CONFLICT (provider_id) DO UPDATE
              SET provider_name = EXCLUDED.provider_name,
                  organisation_type = COALESCE(EXCLUDED.organisation_type, registry.providers.organisation_type),
                  updated_at = now()
            """,
            providers,
        )
        stats["provider_inserts"] = len(providers)
        conn.commit()

        previous = None
        for year in years:
            current = services[services["year"] == year].drop_duplicates("service_id")
            if previous is None:
                cur.executemany(INSERT_SERVICE, [_service_tuple(row) for row in current.itertuples(index=False)])
                stats["service_inserts"] += len(current)
            else:
                diff = diff_year(previous, current)
                by_id = {row.service_id: row for row in current.itertuples(index=False)}
                if diff.inserts:
                    cur.executemany(
                        INSERT_SERVICE,
                        [_service_tuple(by_id[service_id]) for service_id in diff.inserts],
                    )
                    stats["service_inserts"] += len(diff.inserts)
                if diff.updates:
                    updates = []
                    for service_id in diff.updates:
                        payload = _service_tuple(by_id[service_id])
                        updates.append((*payload[1:], payload[0]))
                    cur.executemany(UPDATE_SERVICE, updates)
                    stats["service_updates"] += len(diff.updates)
                if diff.deletes:
                    cur.execute(
                        "DELETE FROM registry.services WHERE service_id = ANY(%s)",
                        (diff.deletes,),
                    )
                    stats["service_deletes"] += len(diff.deletes)
            cur.executemany(
                """
                INSERT INTO registry.places_by_year (
                    service_id, year, residential_places, home_care_places, restorative_places,
                    state_code, acpr_name, care_type
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [_place_tuple(row) for row in current.itertuples(index=False)],
            )
            stats["place_inserts"] += len(current)
            conn.commit()
            previous = current
    stats["rows_touched"] = (
        stats["provider_inserts"]
        + stats["service_inserts"]
        + stats["service_updates"]
        + stats["service_deletes"]
        + stats["place_inserts"]
    )
    return stats


def main() -> None:
    print("Waiting for Debezium to stream…")
    wait_for_streaming()
    services = assign_service_ids(load_all_service_lists())
    with _connect() as conn:
        reset_tables(conn)
        stats = replay(conn, services)
    GOLD.mkdir(parents=True, exist_ok=True)
    path = GOLD / "replay_stats.json"
    path.write_text(json.dumps(stats, indent=2))
    emit_job(
        name="replay_service_registry",
        inputs=["snapshot/gen/service_list_2021_2025"],
        outputs=["postgres/registry.services", "postgres/registry.places_by_year", "gold/replay_stats.json"],
    )
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
