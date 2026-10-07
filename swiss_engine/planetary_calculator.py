from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, cast

try:
    import swisseph as swe
except ImportError as exc:  # pragma: no cover
    swe = None
    SWISS_IMPORT_ERROR = exc
else:
    SWISS_IMPORT_ERROR = None

from backend.utils.constants import PLANETS
from backend.models.schemas import PersonDetails
from backend.swiss_engine.nakshatra_calculator import nakshatra_from_longitude, sign_from_longitude


PLANET_IDS = {
    "Sun": 0,
    "Moon": 1,
    "Mars": 4,
    "Mercury": 2,
    "Jupiter": 5,
    "Venus": 3,
    "Saturn": 6,
    "Rahu": 10,
}


class SwissEphemerisCalculator:
    def __init__(self) -> None:
        if swe is None:
            raise RuntimeError("pyswisseph is required for Swiss Ephemeris calculations") from SWISS_IMPORT_ERROR
        self._swe = cast(Any, swe)
        self._swe.set_sid_mode(self._swe.SIDM_LAHIRI)

    def julian_day_ut(self, person: PersonDetails) -> float:
        local_dt = datetime.combine(person.dob, person.tob)
        utc_dt = local_dt - timedelta(hours=person.timezone)
        return self.julian_day_from_utc(utc_dt)

    def julian_day_from_utc(self, utc_dt: datetime) -> float:
        return self._swe.julday(
            utc_dt.year,
            utc_dt.month,
            utc_dt.day,
            utc_dt.hour + utc_dt.minute / 60 + utc_dt.second / 3600,
        )

    def planet_positions(self, person: PersonDetails) -> dict[str, dict[str, float | str | int | bool]]:
        jd_ut = self.julian_day_ut(person)
        return self.planet_positions_from_julian_day(jd_ut)

    def planet_positions_from_julian_day(self, jd_ut: float) -> dict[str, dict[str, float | str | int | bool]]:
        positions: dict[str, dict[str, float | str | int | bool]] = {}
        flags = self._swe.FLG_SWIEPH | self._swe.FLG_SIDEREAL

        for planet, planet_id in PLANET_IDS.items():
            result = self._swe.calc_ut(jd_ut, planet_id, flags)[0]
            longitude = result[0] % 360
            speed = result[3] if len(result) > 3 else 0.0
            sign, sign_number = sign_from_longitude(longitude)
            nakshatra, nakshatra_number, pada = nakshatra_from_longitude(longitude)
            positions[planet] = {
                "longitude": round(longitude, 6),
                "speed": round(speed, 6),
                "retrograde": speed < 0,
                "sign": sign,
                "sign_number": sign_number,
                "nakshatra": nakshatra,
                "nakshatra_number": nakshatra_number,
                "pada": pada,
            }

        rahu_longitude = float(positions["Rahu"]["longitude"])
        ketu_longitude = (rahu_longitude + 180) % 360
        sign, sign_number = sign_from_longitude(ketu_longitude)
        nakshatra, nakshatra_number, pada = nakshatra_from_longitude(ketu_longitude)
        positions["Ketu"] = {
            "longitude": round(ketu_longitude, 6),
            "speed": round(-float(positions["Rahu"].get("speed", 0.0)), 6),
            "retrograde": bool(positions["Rahu"].get("retrograde", False)),
            "sign": sign,
            "sign_number": sign_number,
            "nakshatra": nakshatra,
            "nakshatra_number": nakshatra_number,
            "pada": pada,
        }

        return {planet: positions[planet] for planet in PLANETS}

    def planet_positions_at_utc(self, utc_dt: datetime) -> dict[str, dict[str, float | str | int | bool]]:
        return self.planet_positions_from_julian_day(self.julian_day_from_utc(utc_dt))

    def ascendant(self, person: PersonDetails) -> dict[str, float | str | int | list[float]]:
        jd_ut = self.julian_day_ut(person)
        try:
            cusps, ascmc = self._swe.houses_ex(
                jd_ut,
                person.latitude,
                person.longitude,
                b"P",
                self._swe.FLG_SIDEREAL,
            )
        except TypeError:
            cusps, ascmc = self._swe.houses_ex(jd_ut, person.latitude, person.longitude, b"P")
        longitude = ascmc[0] % 360
        sign, sign_number = sign_from_longitude(longitude)
        nakshatra, nakshatra_number, pada = nakshatra_from_longitude(longitude)
        return {
            "longitude": round(longitude, 6),
            "sign": sign,
            "sign_number": sign_number,
            "nakshatra": nakshatra,
            "nakshatra_number": nakshatra_number,
            "pada": pada,
            "house_cusps": [round(cusp % 360, 6) for cusp in cusps[:12]],
        }
