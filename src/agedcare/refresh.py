"""Re-download the public source files and rewrite data/snapshot/manifest.json.

`make refresh` needs the network. CI and the dashboard do not. They read the
committed snapshot.
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from agedcare.paths import SNAPSHOT

# Licences are the wording on the publisher's page, checked 10 November 2026 (AEDT).
GEN_LICENCE = (
    "Creative Commons BY 4.0 (CC-BY 4.0). "
    "GEN copyright page: 'Material that can be copied or downloaded from this website "
    "has been released under a Creative Commons BY 4.0 (CC-BY 4.0) licence.' "
    "https://www.gen-agedcaredata.gov.au/copyright"
)
ABS_LICENCE = (
    "Creative Commons Attribution 4.0 International. "
    "ABS copyright page: 'All material presented on this website is provided under a "
    "Creative Commons Attribution 4.0 International licence', with stated exceptions "
    "that do not include these statistical tables. https://www.abs.gov.au/copyright"
)
GEO_LICENCE = (
    "2018 Aged Care Planning Region boundaries from the Department of Health, "
    "hosted as the public AIHW feature service Aged_Care_Planning_Regions_2018 "
    "(layer DOH_ACPR_2018_simplify_island). The feature service does not publish a "
    "separate licence string. AIHW website downloads are released under Creative "
    "Commons BY 4.0 except material that carries its own notice: "
    "https://www.gen-agedcaredata.gov.au/copyright"
)

GEN = "https://www.gen-agedcaredata.gov.au"
ABS = "https://www.abs.gov.au"
SOURCES = [
    {
        "path": "gen/curf_2025.xlsx",
        "url": f"{GEN}/getmedia/62eab216-72b9-4ee6-8fdc-4fed7cc9580e/CURF_Providers-of-aged-care_2025",
        "publisher": "Australian Institute of Health and Welfare",
        "licence": GEN_LICENCE,
        "page": f"{GEN}/resources/access-data/2026/may/gen-data-providers-of-aged-care",
    },
    {
        "path": "gen/curf_2024.xlsx",
        "url": f"{GEN}/getmedia/ef178318-9e37-4f0a-a26f-ec592defd434/CURF_Providers-services-and-places-in-aged-care-2024",
        "publisher": "Australian Institute of Health and Welfare",
        "licence": GEN_LICENCE,
        "page": f"{GEN}/resources/access-data/2026/may/gen-data-providers-of-aged-care",
    },
    {
        "path": "gen/curf_2023.csv",
        "url": f"{GEN}/getmedia/5285e07e-6b1d-41df-9461-1e74af5b6606/ServicesPlaces_2022to2023_GENdata_",
        "publisher": "Australian Institute of Health and Welfare",
        "licence": GEN_LICENCE,
        "page": f"{GEN}/resources/access-data/2026/may/gen-data-providers-of-aged-care",
    },
    {
        "path": "gen/curf_2022.csv",
        "url": f"{GEN}/getmedia/c25fd0f5-3752-4cc6-bf36-5e4e5007d5e3/ServicesPlaces_2021to2022_GENdata",
        "publisher": "Australian Institute of Health and Welfare",
        "licence": GEN_LICENCE,
        "page": f"{GEN}/resources/access-data/2026/may/gen-data-providers-of-aged-care",
    },
    {
        "path": "gen/curf_2021.csv",
        "url": f"{GEN}/getmedia/4240a016-1a8d-40de-a589-8ce2db503304/ServicesPlaces_2020to2021_GENdata.csv",
        "publisher": "Australian Institute of Health and Welfare",
        "licence": GEN_LICENCE,
        "page": f"{GEN}/resources/access-data/2026/may/gen-data-providers-of-aged-care",
    },
    {
        "path": "gen/curf_2020.csv",
        "url": f"{GEN}/getmedia/9c830abe-9851-466d-b428-efd03c4ef5d5/ServicesPlaces_2019to2020_GENdata.csv",
        "publisher": "Australian Institute of Health and Welfare",
        "licence": GEN_LICENCE,
        "page": f"{GEN}/resources/access-data/2026/may/gen-data-providers-of-aged-care",
    },
    {
        "path": "gen/curf_2019.csv",
        "url": f"{GEN}/getmedia/a24b98b4-c6ee-4ff7-bd7c-69eee8355e91/Services-and-places-in-aged-care-30-June-2019.csv",
        "publisher": "Australian Institute of Health and Welfare",
        "licence": GEN_LICENCE,
        "page": f"{GEN}/resources/access-data/2026/may/gen-data-providers-of-aged-care",
    },
    {
        "path": "gen/curf_2008_2018.csv",
        "url": f"{GEN}/getmedia/9917bea1-01d2-4241-b237-0fd439355225/Services-and-places-in-aged-care,-30-June-2008-2018.csv",
        "publisher": "Australian Institute of Health and Welfare",
        "licence": GEN_LICENCE,
        "page": f"{GEN}/resources/access-data/2026/may/gen-data-providers-of-aged-care",
    },
    {
        "path": "gen/service_list_2025_australia.xlsx",
        "url": f"{GEN}/getmedia/2599a590-3c5f-4227-aac3-f0a3a8aa84e4/Service-List-2025-Australia_300126",
        "publisher": "Department of Health, Disability and Ageing",
        "licence": GEN_LICENCE,
        "page": f"{GEN}/resources/access-data/2025/october/aged-care-service-list-30-june-2025",
    },
    {
        "path": "gen/service_list_2024_australia.xlsx",
        "url": f"{GEN}/getmedia/6848574d-f73d-45ff-a05a-89ad8a01952e/Service-List-30-Jun-2024-Australia",
        "publisher": "Department of Health, Disability and Ageing",
        "licence": GEN_LICENCE,
        "page": f"{GEN}/resources/access-data/2024/september/aged-care-service-list-30-june-2024",
    },
    {
        "path": "gen/service_list_2023_australia.xlsx",
        "url": f"{GEN}/getmedia/26185106-17e3-42d9-9c15-1e358b970030/Australia-Service-List-2023.xlsx",
        "publisher": "Department of Health, Disability and Ageing",
        "licence": GEN_LICENCE,
        "page": f"{GEN}/resources/access-data/2023/september/aged-care-service-list-30-june-2023",
    },
    {
        "path": "gen/service_list_2022_australia.xlsx",
        "url": f"{GEN}/getmedia/6ad31151-56b1-4b21-9469-0b5256807160/Australia_30-June-2022.xlsx",
        "publisher": "Department of Health, Disability and Ageing",
        "licence": GEN_LICENCE,
        "page": f"{GEN}/resources/access-data/2022/october/aged-care-service-list-30-june-2022",
    },
    {
        "path": "gen/service_list_2021_australia.xlsx",
        "url": f"{GEN}/getmedia/d5e51a4f-bddf-48a6-bffe-434232488adb/Australia_30-June-2021.xlsx",
        "publisher": "Department of Health, Disability and Ageing",
        "licence": GEN_LICENCE,
        "page": f"{GEN}/resources/access-data/2021/october/aged-care-service-list-30-june-2021",
    },
    {
        "path": "gen/stocktake_acpr_places_2025.xlsx",
        "url": f"{GEN}/getmedia/c276f91f-fcaa-4aff-aac2-58d303687a8f/2024-25-2-ACPR-Operational-Places-and-Ratios",
        "publisher": "Department of Health, Disability and Ageing",
        "licence": GEN_LICENCE,
        "page": f"{GEN}/resources/access-data/2025/october/stocktake-data-30-june-2025",
    },
    {
        "path": "gen/stocktake_comparison_2015_2025.xlsx",
        "url": f"{GEN}/getmedia/0fc99b10-a0f9-4fcb-95b6-54127d1232de/2024-25-7-Comparison-30-June-2015-30-June-2025",
        "publisher": "Department of Health, Disability and Ageing",
        "licence": GEN_LICENCE,
        "page": f"{GEN}/resources/access-data/2025/october/stocktake-data-30-june-2025",
    },
    {
        "path": "abs/erp_q_age70plus_2014_2026.csv",
        "url": "https://data.api.abs.gov.au/rest/data/ABS,ERP_Q,1.0.0/1.3.70+71+72+73+74+75+76+77+78+79+80+81+82+83+84+85+86+87+88+89+90+91+92+93+94+95+96+97+98+99+100+A99.AUS+1+2+3+4+5+6+7+8.Q?startPeriod=2014-Q2&endPeriod=2026-Q2&dimensionAtObservation=AllDimensions&format=csv",
        "publisher": "Australian Bureau of Statistics",
        "licence": ABS_LICENCE,
        "page": "https://www.abs.gov.au/statistics/people/population/national-state-and-territory-population/latest-release",
    },
]


def _projection_sources() -> list[dict]:
    rows = []
    for index, state in enumerate(
        ["New South Wales", "Victoria", "Queensland", "South Australia", "Western Australia", "Tasmania", "Northern Territory", "Australian Capital Territory", "Australia"],
        start=1,
    ):
        rows.append(
            {
                "path": f"abs/proj/3222_Table_B{index}.xlsx",
                "url": f"{ABS}/statistics/people/population/population-projections-australia/2022-base-2071/3222_Table_B{index}.xlsx",
                "publisher": "Australian Bureau of Statistics",
                "licence": ABS_LICENCE,
                "page": f"{ABS}/statistics/people/population/population-projections-australia/latest-release",
                "note": f"Table B{index}. Population projections by age and sex, {state}, series 29 (medium).",
            }
        )
    return rows


def _geo_source() -> dict:
    return {
        "path": "geo/acpr_2018.geojson",
        "url": "https://maps.arcgis.aihw.gov.au/server/rest/services/Hosted/Aged_Care_Planning_Regions_2018/FeatureServer/0/query?where=1%3D1&outFields=state_terr,acpr_code,acpr_name&returnGeometry=true&outSR=4326&f=geojson&geometryPrecision=4",
        "publisher": "Department of Health, Disability and Ageing, via AIHW map service",
        "licence": GEO_LICENCE,
        "page": "https://maps.arcgis.aihw.gov.au/server/rest/services/Hosted/Aged_Care_Planning_Regions_2018/FeatureServer",
    }


def all_sources() -> list[dict]:
    return [*SOURCES, *_projection_sources(), _geo_source()]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rows(path: Path) -> int | None:
    if path.suffix.lower() == ".csv":
        with path.open("rb") as handle:
            return max(sum(1 for _ in handle) - 1, 0)
    if path.suffix.lower() == ".geojson":
        payload = json.loads(path.read_text())
        return len(payload.get("features", []))
    if path.suffix.lower() == ".xlsx":
        from openpyxl import load_workbook

        workbook = load_workbook(path, read_only=True, data_only=True)
        sheet = workbook.active
        count = sum(1 for _ in sheet.iter_rows(values_only=True))
        workbook.close()
        return count
    return None


def write_manifest(downloaded: bool) -> Path:
    access = datetime.now(ZoneInfo("Australia/Sydney")).strftime("%Y-%m-%d %H:%M %Z")
    files = []
    for source in all_sources():
        path = SNAPSHOT / source["path"]
        if not path.exists():
            raise FileNotFoundError(path)
        files.append(
            {
                "path": source["path"],
                "url": source["url"],
                "publisher": source["publisher"],
                "page": source["page"],
                "licence": source["licence"],
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
                "row_count": _rows(path),
                "access_date_aedt": access,
                "note": source.get("note", ""),
                "free": "Free public download. No account and no API key.",
            }
        )
    document = {
        "downloaded_this_run": downloaded,
        "access_note": "Timestamps are Australia/Sydney, which is AEDT in November.",
        "files": files,
    }
    target = SNAPSHOT / "manifest.json"
    target.write_text(json.dumps(document, indent=2))
    return target


def download() -> None:
    for source in all_sources():
        target = SNAPSHOT / source["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        print("GET", source["url"])
        request = urllib.request.Request(source["url"], headers={"User-Agent": "aged-care-bed-block"})
        with urllib.request.urlopen(request, timeout=180) as response:
            target.write_bytes(response.read())
    write_manifest(downloaded=True)


def main() -> None:
    download()


if __name__ == "__main__":
    main()
