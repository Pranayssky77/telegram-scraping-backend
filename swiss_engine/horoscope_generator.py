from __future__ import annotations

from backend.models.schemas import PersonDetails
from backend.swiss_engine.chart_analysis import ChartAnalyzer
from backend.swiss_engine.marriage_timing import MarriageTimingAnalyzer
from backend.swiss_engine.planetary_calculator import SwissEphemerisCalculator


class HoroscopeGenerator:
    def __init__(self, calculator: SwissEphemerisCalculator | None = None) -> None:
        self.calculator = calculator or SwissEphemerisCalculator()
        self.chart_analyzer = ChartAnalyzer()
        self.marriage_timing = MarriageTimingAnalyzer(self.calculator)

    def generate(self, person: PersonDetails, include_timing: bool = True) -> dict:
        planets = self.calculator.planet_positions(person)
        ascendant = self.calculator.ascendant(person)
        moon = planets["Moon"]
        horoscope = {
            "person": person.name,
            "planets": planets,
            "ascendant": ascendant,
            "moon_sign": moon["sign"],
            "moon_sign_number": moon["sign_number"],
            "moon_nakshatra": moon["nakshatra"],
            "moon_nakshatra_number": moon["nakshatra_number"],
            "moon_pada": moon["pada"],
        }
        analysis = self.chart_analyzer.analyze(horoscope)
        horoscope["analysis"] = analysis
        if include_timing:
            horoscope["marriage_timing"] = self.marriage_timing.analyze(person, horoscope)
        return horoscope
