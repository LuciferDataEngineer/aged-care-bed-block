"""Shared helpers: geography names, numbers, and JSON cleaning."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any

STATE_NAMES = {
    "NSW": "New South Wales",
    "VIC": "Victoria",
    "QLD": "Queensland",
    "SA": "South Australia",
    "WA": "Western Australia",
    "TAS": "Tasmania",
    "NT": "Northern Territory",
    "ACT": "Australian Capital Territory",
    "AUS": "Australia",
}

STATE_ORDER = ["NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT"]

# ABS ERP_Q / ASGS state codes.
ABS_REGION = {
    "AUS": "AUS",
    "0": "AUS",
    "1": "NSW",
    "2": "VIC",
    "3": "QLD",
    "4": "SA",
    "5": "WA",
    "6": "TAS",
    "7": "NT",
    "8": "ACT",
}

# Historical residential component of the Commonwealth target provision ratio
# (78 residential + 2 restorative + 45 home care = 125 places per 1,000 people
# aged 70+). Used here as a planning yardstick, not a measure of clinical need.
BENCHMARK_PER_1000 = 78.0

# Reported by states via ABC. Not computed from the datasets in this repo.
REPORTED = {
    "sa_hospital_patients_waiting": {
        "label": "More than 500",
        "value_low": 500,
        "comparison_label": "about 60",
        "comparison_value": 60,
        "comparison_when": "four years earlier (around October 2022, SA Health figures reported in September 2026)",
        "statement": (
            "More than 500 older patients are in South Australian public hospitals "
            "waiting for a residential aged care placement, up from about 60 four years ago."
        ),
        "sources": [
            {
                "publisher": "ABC Radio National Breakfast",
                "title": "Hospitals 'paying the price' for lack of federal action on aged care, SA Premier says",
                "url": "https://www.abc.net.au/listen/programs/radionational-breakfast/radio-national-breakfast-sa-premier-aged-care/107366264",
                "date": "10 November 2026, 7:30 am AEDT",
            },
            {
                "publisher": "ABC News",
                "title": "Australia's aged care bed crisis hits boiling point for families waiting years",
                "url": "https://www.abc.net.au/news/2026-11-09/residential-aged-care-bed-waitlist-south-australia-families/107341030",
                "date": "9 November 2026",
            },
        ],
    },
    "national_places_needed_per_year": {
        "value": 10600,
        "statement": (
            "South Australia's Health Minister said at least 10,600 additional federal "
            "residential aged care places are needed nationally each year over the next two decades."
        ),
        "source": "ABC News, 9 November 2026, quoting SA Health Minister Blair Boyer",
        "url": "https://www.abc.net.au/news/2026-11-09/residential-aged-care-bed-waitlist-south-australia-families/107341030",
    },
    "national_places_added_last_year_reported": {
        "value": 800,
        "statement": "The same minister said that last year just 800 beds were added to the system.",
        "source": "ABC News, 9 November 2026, quoting SA Health Minister Blair Boyer",
        "url": "https://www.abc.net.au/news/2026-11-09/residential-aged-care-bed-waitlist-south-australia-families/107341030",
    },
    "federal_construction_claim": {
        "value": 5000,
        "statement": (
            "A federal spokesperson told the ABC the government is supporting the construction "
            "of around 5,000 additional residential aged care beds nationally each year."
        ),
        "source": "ABC News, 9 November 2026",
        "url": "https://www.abc.net.au/news/2026-11-09/residential-aged-care-bed-waitlist-south-australia-families/107341030",
    },
}


def canon_state(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return None
    key = re.sub(r"\s+", " ", text).strip().lower()
    aliases = {
        "nsw": "NSW",
        "new south wales": "NSW",
        "vic": "VIC",
        "victoria": "VIC",
        "qld": "QLD",
        "queensland": "QLD",
        "wa": "WA",
        "western australia": "WA",
        "sa": "SA",
        "south australia": "SA",
        "tas": "TAS",
        "tasmania": "TAS",
        "act": "ACT",
        "australian capital territory": "ACT",
        "nt": "NT",
        "northern territory": "NT",
        "australia": "AUS",
        "aus": "AUS",
    }
    if key in aliases:
        return aliases[key]
    if text in ABS_REGION:
        return ABS_REGION[text]
    return None


def norm_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.lower().replace("&", " and ")
    text = text.replace("–", " ").replace("—", " ").replace("-", " ").replace("/", " ")
    text = text.replace(",", " ").replace("'", "").replace(".", " ")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def norm_region(value: Any) -> str:
    return norm_text(value)


def to_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return int(round(value))
    text = str(value).strip().replace(",", "").replace(" ", "")
    if text.lower() in {"", "-", "–", "—", "na", "n/a", "null", "."}:
        return None
    try:
        return int(round(float(text)))
    except ValueError:
        return None


def to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return number
    text = str(value).strip().replace(",", "")
    if text.lower() in {"", "-", "–", "—", "na", "n/a", "null"}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def sha_id(*parts: Any, n: int = 16) -> str:
    key = "|".join(norm_text(part) for part in parts)
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:n]


def clean_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): clean_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_json(v) for v in value]
    if hasattr(value, "item") and callable(value.item):
        try:
            return clean_json(value.item())
        except Exception:
            pass
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def ratio(places: float | None, population: float | None) -> float | None:
    if places is None or population is None or population <= 0:
        return None
    return places / population * 1000.0


def shortfall(places: float | None, population: float | None, benchmark: float = BENCHMARK_PER_1000) -> float | None:
    """Places still required to reach the benchmark. Negative means a surplus."""
    if places is None or population is None or population <= 0:
        return None
    return benchmark * population / 1000.0 - places


def status_for_ratio(value: float | None, benchmark: float = BENCHMARK_PER_1000) -> str:
    if value is None:
        return "amber"
    if value >= benchmark:
        return "green"
    if value >= benchmark - 8:
        return "amber"
    return "red"
