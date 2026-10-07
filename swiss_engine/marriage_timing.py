from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any

from backend.models.schemas import PersonDetails
from backend.swiss_engine.chart_analysis import (
    DUSTHANA_HOUSES,
    KENDRA_HOUSES,
    SIGN_LORD,
    dignity,
    sign_distance,
)
from backend.swiss_engine.dasha_calculator import DASHA_SEQUENCE, DASHA_YEARS, DashaCalculator
from backend.swiss_engine.dosha_calculator import house_from_lagna
from backend.swiss_engine.planetary_calculator import SwissEphemerisCalculator


MARRIAGE_SUPPORTING_DASHA_LORDS = {"Venus", "Jupiter", "Moon", "Mercury"}
MARRIAGE_SUPPORTING_JUPITER_HOUSES = {2, 5, 7, 9, 11}
MARRIAGE_SUPPORTING_SATURN_HOUSES = {3, 5, 7, 10, 11}


class MarriageTimingAnalyzer:
    def __init__(
        self,
        calculator: SwissEphemerisCalculator | None = None,
        dasha_calculator: DashaCalculator | None = None,
    ) -> None:
        self.calculator = calculator or SwissEphemerisCalculator()
        self.dasha_calculator = dasha_calculator or DashaCalculator()

    def analyze(
        self,
        person: PersonDetails,
        horoscope: dict[str, Any],
        start_year: int | None = None,
        years: int = 16,
    ) -> dict[str, Any]:
        start = start_year or date.today().year
        yearly = [self._score_year(person, horoscope, year) for year in range(start, start + years)]
        windows = self._windows(yearly)
        best_years = sorted(yearly, key=lambda item: item["score"], reverse=True)[:5]
        return {
            "start_year": start,
            "end_year": start + years - 1,
            "best_years": sorted(best_years, key=lambda item: item["year"]),
            "windows": windows,
            "yearly_scores": yearly,
        }

    def _score_year(self, person: PersonDetails, horoscope: dict[str, Any], year: int) -> dict[str, Any]:
        transit_date = datetime(year, 7, 1, 12, 0, tzinfo=timezone.utc).replace(tzinfo=None)
        transits = self.calculator.planet_positions_at_utc(transit_date)
        lagna_sign = int(horoscope["ascendant"]["sign_number"])
        moon_sign = int(horoscope["moon_sign_number"])
        seventh_sign = ((lagna_sign + 7 - 2) % 12) + 1
        seventh_lord = SIGN_LORD[seventh_sign]
        natal_venus = horoscope["planets"]["Venus"]
        natal_jupiter = horoscope["planets"]["Jupiter"]
        dasha = self._dasha_for_year(person, horoscope, year)

        score = 35.0
        reasons: list[str] = []

        jupiter_sign = int(transits["Jupiter"]["sign_number"])
        jupiter_from_moon = sign_distance(moon_sign, jupiter_sign)
        jupiter_from_lagna = house_from_lagna(jupiter_sign, lagna_sign)
        if jupiter_from_moon in MARRIAGE_SUPPORTING_JUPITER_HOUSES:
            score += 18
            reasons.append(f"Jupiter supports marriage from Moon house {jupiter_from_moon}")
        if jupiter_from_lagna in MARRIAGE_SUPPORTING_JUPITER_HOUSES:
            score += 12
            reasons.append(f"Jupiter supports Lagna house {jupiter_from_lagna}")

        saturn_sign = int(transits["Saturn"]["sign_number"])
        saturn_from_moon = sign_distance(moon_sign, saturn_sign)
        if saturn_from_moon in MARRIAGE_SUPPORTING_SATURN_HOUSES:
            score += 8
            reasons.append(f"Saturn gives stabilizing support from Moon house {saturn_from_moon}")
        elif saturn_from_moon in DUSTHANA_HOUSES:
            score -= 8
            reasons.append(f"Saturn transit is heavier from Moon house {saturn_from_moon}")

        if dasha["mahadasha_lord"] in MARRIAGE_SUPPORTING_DASHA_LORDS:
            score += 12
            reasons.append(f"{dasha['mahadasha_lord']} mahadasha is marriage-supportive")
        if dasha["antardasha_lord"] in {seventh_lord, "Venus", "Jupiter", "Moon"}:
            score += 12
            reasons.append(f"{dasha['antardasha_lord']} antardasha activates relationship themes")

        seventh_lord_dignity = dignity(seventh_lord, int(horoscope["planets"][seventh_lord]["sign_number"]))
        if seventh_lord_dignity["score"] >= 75:
            score += 6
            reasons.append("Seventh lord is strong in the natal chart")
        if house_from_lagna(int(natal_venus["sign_number"]), lagna_sign) in KENDRA_HOUSES:
            score += 5
            reasons.append("Natal Venus is placed in a kendra")
        if house_from_lagna(int(natal_jupiter["sign_number"]), lagna_sign) in KENDRA_HOUSES:
            score += 5
            reasons.append("Natal Jupiter is placed in a kendra")

        score = round(max(0.0, min(100.0, score)), 2)
        if score >= 75:
            grade = "excellent"
        elif score >= 60:
            grade = "good"
        elif score >= 45:
            grade = "average"
        else:
            grade = "challenging"
        return {
            "year": year,
            "score": score,
            "grade": grade,
            "dasha": dasha,
            "transits": {
                "Jupiter": {
                    "sign": transits["Jupiter"]["sign"],
                    "house_from_moon": jupiter_from_moon,
                    "house_from_lagna": jupiter_from_lagna,
                },
                "Saturn": {
                    "sign": transits["Saturn"]["sign"],
                    "house_from_moon": saturn_from_moon,
                    "house_from_lagna": house_from_lagna(saturn_sign, lagna_sign),
                },
            },
            "reasons": reasons or ["No strong marriage timing activation found"],
        }

    def _dasha_for_year(
        self,
        person: PersonDetails,
        horoscope: dict[str, Any],
        year: int,
    ) -> dict[str, Any]:
        birth_dasha = self.dasha_calculator.vimshottari_at_birth(horoscope)
        birth_dt = datetime.combine(person.dob, person.tob)
        target_dt = datetime.combine(date(year, 7, 1), time(12, 0))
        age_years = max(0.0, (target_dt - birth_dt).days / 365.2425)
        lord = birth_dasha["mahadasha_lord"]
        remaining = float(birth_dasha["balance_years_at_birth"])
        remaining_age = age_years
        index = DASHA_SEQUENCE.index(lord)
        if remaining_age <= remaining:
            maha_lord = lord
            elapsed_in_maha = DASHA_YEARS[lord] - remaining + remaining_age
        else:
            remaining_age -= remaining
            index = (index + 1) % len(DASHA_SEQUENCE)
            while remaining_age > DASHA_YEARS[DASHA_SEQUENCE[index]]:
                remaining_age -= DASHA_YEARS[DASHA_SEQUENCE[index]]
                index = (index + 1) % len(DASHA_SEQUENCE)
            maha_lord = DASHA_SEQUENCE[index]
            elapsed_in_maha = remaining_age

        maha_years = DASHA_YEARS[maha_lord]
        antar_cursor = 0.0
        antardasha_lord = DASHA_SEQUENCE[index]
        for offset in range(len(DASHA_SEQUENCE)):
            antar_lord = DASHA_SEQUENCE[(index + offset) % len(DASHA_SEQUENCE)]
            antar_years = maha_years * DASHA_YEARS[antar_lord] / 120.0
            if elapsed_in_maha <= antar_cursor + antar_years:
                antardasha_lord = antar_lord
                break
            antar_cursor += antar_years

        return {
            "mahadasha_lord": maha_lord,
            "antardasha_lord": antardasha_lord,
            "age_years": round(age_years, 2),
        }

    def _windows(self, yearly: list[dict[str, Any]]) -> list[dict[str, Any]]:
        windows: list[dict[str, Any]] = []
        active: list[dict[str, Any]] = []
        for item in yearly:
            if item["score"] >= 60:
                active.append(item)
                continue
            if active:
                windows.append(self._window_from_years(active))
                active = []
        if active:
            windows.append(self._window_from_years(active))
        return windows

    def _window_from_years(self, years: list[dict[str, Any]]) -> dict[str, Any]:
        avg_score = round(sum(float(item["score"]) for item in years) / len(years), 2)
        return {
            "from_year": years[0]["year"],
            "to_year": years[-1]["year"],
            "average_score": avg_score,
            "grade": "excellent" if avg_score >= 75 else "good",
            "peak_year": max(years, key=lambda item: item["score"])["year"],
        }
