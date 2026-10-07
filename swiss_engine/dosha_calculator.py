from __future__ import annotations


KUJA_HOUSES = {1, 2, 4, 7, 8, 12}
KUJA_CANCELLATION_SIGNS = {1, 4, 8, 10}


def house_from_lagna(planet_sign_number: int, lagna_sign_number: int) -> int:
    return ((planet_sign_number - lagna_sign_number) % 12) + 1


class DoshaCalculator:
    def kuja_dosha(self, horoscope: dict) -> dict:
        lagna_sign = int(horoscope["ascendant"]["sign_number"])
        mars_sign = int(horoscope["planets"]["Mars"]["sign_number"])
        moon_sign = int(horoscope["moon_sign_number"])
        mars_house_from_lagna = house_from_lagna(mars_sign, lagna_sign)
        mars_house_from_moon = house_from_lagna(mars_sign, moon_sign)
        has_dosha = mars_house_from_lagna in KUJA_HOUSES or mars_house_from_moon in KUJA_HOUSES
        cancellations = self._kuja_cancellations(horoscope, mars_sign, mars_house_from_lagna, mars_house_from_moon)
        severity = 0
        if mars_house_from_lagna in KUJA_HOUSES:
            severity += 1
        if mars_house_from_moon in KUJA_HOUSES:
            severity += 1
        adjusted_severity = max(0, severity - len(cancellations))
        return {
            "has_kuja_dosha": has_dosha,
            "has_manglik_dosha": has_dosha,
            "severity": severity,
            "adjusted_severity": adjusted_severity,
            "is_cancelled": has_dosha and adjusted_severity == 0,
            "cancellations": cancellations,
            "mars_house_from_lagna": mars_house_from_lagna,
            "mars_house_from_moon": mars_house_from_moon,
        }

    def _kuja_cancellations(
        self,
        horoscope: dict,
        mars_sign: int,
        mars_house_from_lagna: int,
        mars_house_from_moon: int,
    ) -> list[str]:
        planets = horoscope["planets"]
        cancellations: list[str] = []
        if mars_sign in KUJA_CANCELLATION_SIGNS:
            cancellations.append("Mars is in own/exaltation/debilitation cancellation sign group")
        if mars_house_from_lagna in {1, 4, 7, 8, 12} and mars_sign in {1, 4, 7, 8, 10}:
            cancellations.append("Mars house/sign combination reduces Kuja dosha severity")
        jupiter_sign = int(planets["Jupiter"]["sign_number"])
        venus_sign = int(planets["Venus"]["sign_number"])
        if jupiter_sign == mars_sign:
            cancellations.append("Jupiter conjunct Mars")
        if venus_sign == mars_sign:
            cancellations.append("Venus conjunct Mars")
        if house_from_lagna(jupiter_sign, mars_sign) in {5, 7, 9}:
            cancellations.append("Jupiter aspects Mars by sign")
        if house_from_lagna(venus_sign, mars_sign) == 7:
            cancellations.append("Venus aspects Mars by sign")
        if mars_house_from_moon == 2 and mars_sign in {3, 6}:
            cancellations.append("Mars in 2nd from Moon in Gemini/Virgo cancellation")
        if mars_house_from_moon == 12 and mars_sign in {2, 7}:
            cancellations.append("Mars in 12th from Moon in Taurus/Libra cancellation")
        return cancellations
