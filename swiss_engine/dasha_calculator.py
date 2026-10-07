from __future__ import annotations

from backend.swiss_engine.nakshatra_calculator import NAKSHATRA_SPAN

DASHA_SEQUENCE = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]
DASHA_YEARS = {
    "Ketu": 7,
    "Venus": 20,
    "Sun": 6,
    "Moon": 10,
    "Mars": 7,
    "Rahu": 18,
    "Jupiter": 16,
    "Saturn": 19,
    "Mercury": 17,
}


class DashaCalculator:
    def vimshottari_at_birth(self, horoscope: dict) -> dict:
        nakshatra_number = int(horoscope["moon_nakshatra_number"])
        moon_longitude = float(horoscope["planets"]["Moon"]["longitude"])
        lord = DASHA_SEQUENCE[(nakshatra_number - 1) % 9]
        elapsed_in_star = moon_longitude % NAKSHATRA_SPAN
        remaining_fraction = max(0.0, (NAKSHATRA_SPAN - elapsed_in_star) / NAKSHATRA_SPAN)
        balance_years = DASHA_YEARS[lord] * remaining_fraction
        antar_index = int((1 - remaining_fraction) * 9) % 9
        return {
            "mahadasha_lord": lord,
            "balance_years_at_birth": round(balance_years, 3),
            "antardasha_lord": DASHA_SEQUENCE[(DASHA_SEQUENCE.index(lord) + antar_index) % 9],
        }

