from __future__ import annotations

from backend.utils.constants import NAKSHATRAS, ZODIAC_SIGNS

NAKSHATRA_SPAN = 360.0 / 27.0
PADA_SPAN = NAKSHATRA_SPAN / 4.0


def normalize_longitude(longitude: float) -> float:
    return longitude % 360.0


def sign_from_longitude(longitude: float) -> tuple[str, int]:
    longitude = normalize_longitude(longitude)
    index = int(longitude // 30)
    return ZODIAC_SIGNS[index], index + 1


def nakshatra_from_longitude(longitude: float) -> tuple[str, int, int]:
    longitude = normalize_longitude(longitude)
    index = int(longitude // NAKSHATRA_SPAN)
    pada = int((longitude % NAKSHATRA_SPAN) // PADA_SPAN) + 1
    return NAKSHATRAS[index], index + 1, pada

