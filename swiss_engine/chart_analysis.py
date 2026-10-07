from __future__ import annotations

from typing import Any

from backend.swiss_engine.dosha_calculator import house_from_lagna
from backend.utils.constants import PLANETS, ZODIAC_SIGNS


SIGN_LORD = {
    1: "Mars",
    2: "Venus",
    3: "Mercury",
    4: "Moon",
    5: "Sun",
    6: "Mercury",
    7: "Venus",
    8: "Mars",
    9: "Jupiter",
    10: "Saturn",
    11: "Saturn",
    12: "Jupiter",
}

OWN_SIGNS = {
    "Sun": {5},
    "Moon": {4},
    "Mars": {1, 8},
    "Mercury": {3, 6},
    "Jupiter": {9, 12},
    "Venus": {2, 7},
    "Saturn": {10, 11},
    "Rahu": set(),
    "Ketu": set(),
}

EXALTATION_SIGNS = {
    "Sun": 1,
    "Moon": 2,
    "Mars": 10,
    "Mercury": 6,
    "Jupiter": 4,
    "Venus": 12,
    "Saturn": 7,
    "Rahu": 2,
    "Ketu": 8,
}

DEBILITATION_SIGNS = {
    "Sun": 7,
    "Moon": 8,
    "Mars": 4,
    "Mercury": 12,
    "Jupiter": 10,
    "Venus": 6,
    "Saturn": 1,
    "Rahu": 8,
    "Ketu": 2,
}

COMBUSTION_LIMITS = {
    "Moon": 12.0,
    "Mars": 17.0,
    "Mercury": 14.0,
    "Jupiter": 11.0,
    "Venus": 10.0,
    "Saturn": 15.0,
}

ASPECT_OFFSETS = {
    "Sun": (7,),
    "Moon": (7,),
    "Mars": (4, 7, 8),
    "Mercury": (7,),
    "Jupiter": (5, 7, 9),
    "Venus": (7,),
    "Saturn": (3, 7, 10),
    "Rahu": (5, 7, 9),
    "Ketu": (5, 7, 9),
}

KENDRA_HOUSES = {1, 4, 7, 10}
TRIKONA_HOUSES = {1, 5, 9}
DUSTHANA_HOUSES = {6, 8, 12}
UPACHAYA_HOUSES = {3, 6, 10, 11}


def circular_distance(a: float, b: float) -> float:
    diff = abs((a - b) % 360.0)
    return min(diff, 360.0 - diff)


def sign_name(sign_number: int) -> str:
    return ZODIAC_SIGNS[(sign_number - 1) % 12]


def sign_distance(from_sign: int, to_sign: int) -> int:
    return ((to_sign - from_sign) % 12) + 1


def navamsa_sign(longitude: float) -> tuple[str, int]:
    sign_number = int((longitude % 360.0) // 30.0) + 1
    degree_in_sign = longitude % 30.0
    pada = int(degree_in_sign // (30.0 / 9.0)) + 1
    if sign_number in {1, 4, 7, 10}:
        start = sign_number
    elif sign_number in {2, 5, 8, 11}:
        start = ((sign_number + 8 - 1) % 12) + 1
    else:
        start = ((sign_number + 4 - 1) % 12) + 1
    navamsa_number = ((start + pada - 2) % 12) + 1
    return sign_name(navamsa_number), navamsa_number


def baaladi_avastha(sign_number: int, longitude: float) -> dict[str, Any]:
    degree = longitude % 30.0
    stages = ["Bala", "Kumara", "Yuva", "Vriddha", "Mrita"]
    index = min(4, int(degree // 6.0))
    if sign_number % 2 == 0:
        index = 4 - index
    score_by_stage = {"Bala": 55, "Kumara": 75, "Yuva": 100, "Vriddha": 50, "Mrita": 25}
    stage = stages[index]
    return {"type": "baaladi", "stage": stage, "score": score_by_stage[stage], "degree_in_sign": round(degree, 3)}


def dignity(planet: str, sign_number: int) -> dict[str, Any]:
    if EXALTATION_SIGNS.get(planet) == sign_number:
        return {"status": "exalted", "score": 100}
    if DEBILITATION_SIGNS.get(planet) == sign_number:
        return {"status": "debilitated", "score": 25}
    if sign_number in OWN_SIGNS.get(planet, set()):
        return {"status": "own_sign", "score": 85}
    return {"status": "neutral", "score": 60}


class ChartAnalyzer:
    def analyze(self, horoscope: dict[str, Any]) -> dict[str, Any]:
        lagna_sign = int(horoscope["ascendant"]["sign_number"])
        planets = horoscope["planets"]
        houses = self._houses(lagna_sign, planets)
        combustion = self._combustion(planets)
        avasthas = self._avasthas(planets)
        navamsa = self._navamsa(planets)
        aspects = self._aspects(lagna_sign, planets)
        strengths = self._strengths(lagna_sign, planets, combustion, avasthas)
        house_lords = self._house_lords(lagna_sign, planets, strengths)
        yogas = self._yogas(lagna_sign, planets, strengths)
        return {
            "houses": houses,
            "navamsa": navamsa,
            "combustion": combustion,
            "avasthas": avasthas,
            "aspects": aspects,
            "planet_strengths": strengths,
            "house_lords": house_lords,
            "yogas": yogas,
            "summary_score": self._summary_score(strengths, yogas),
        }

    def _houses(self, lagna_sign: int, planets: dict[str, Any]) -> list[dict[str, Any]]:
        houses = []
        for house in range(1, 13):
            sign_number = ((lagna_sign + house - 2) % 12) + 1
            occupants = [
                planet
                for planet, data in planets.items()
                if house_from_lagna(int(data["sign_number"]), lagna_sign) == house
            ]
            houses.append(
                {
                    "house": house,
                    "sign": sign_name(sign_number),
                    "sign_number": sign_number,
                    "lord": SIGN_LORD[sign_number],
                    "occupants": occupants,
                }
            )
        return houses

    def _combustion(self, planets: dict[str, Any]) -> dict[str, Any]:
        sun_longitude = float(planets["Sun"]["longitude"])
        result = {}
        for planet, limit in COMBUSTION_LIMITS.items():
            distance = circular_distance(float(planets[planet]["longitude"]), sun_longitude)
            result[planet] = {
                "is_combust": distance <= limit,
                "distance_from_sun": round(distance, 3),
                "orb_limit": limit,
                "severity": "high" if distance <= limit * 0.5 else ("medium" if distance <= limit else "none"),
            }
        return result

    def _avasthas(self, planets: dict[str, Any]) -> dict[str, Any]:
        return {
            planet: baaladi_avastha(int(data["sign_number"]), float(data["longitude"]))
            for planet, data in planets.items()
            if planet not in {"Rahu", "Ketu"}
        }

    def _navamsa(self, planets: dict[str, Any]) -> dict[str, Any]:
        result = {}
        for planet, data in planets.items():
            sign, sign_number = navamsa_sign(float(data["longitude"]))
            result[planet] = {"sign": sign, "sign_number": sign_number}
        return result

    def _aspects(self, lagna_sign: int, planets: dict[str, Any]) -> list[dict[str, Any]]:
        aspects = []
        for planet, data in planets.items():
            sign_number = int(data["sign_number"])
            for offset in ASPECT_OFFSETS.get(planet, (7,)):
                target_sign = ((sign_number + offset - 2) % 12) + 1
                aspects.append(
                    {
                        "planet": planet,
                        "aspect": offset,
                        "target_sign": sign_name(target_sign),
                        "target_sign_number": target_sign,
                        "target_house": house_from_lagna(target_sign, lagna_sign),
                    }
                )
        return aspects

    def _strengths(
        self,
        lagna_sign: int,
        planets: dict[str, Any],
        combustion: dict[str, Any],
        avasthas: dict[str, Any],
    ) -> dict[str, Any]:
        strengths = {}
        for planet in PLANETS:
            data = planets[planet]
            sign_number = int(data["sign_number"])
            house = house_from_lagna(sign_number, lagna_sign)
            dign = dignity(planet, sign_number)
            house_score = 70
            if house in KENDRA_HOUSES or house in TRIKONA_HOUSES:
                house_score = 85
            elif house in DUSTHANA_HOUSES:
                house_score = 45
            elif house in UPACHAYA_HOUSES:
                house_score = 75
            avastha_score = avasthas.get(planet, {}).get("score", 60)
            score = dign["score"] * 0.45 + house_score * 0.25 + avastha_score * 0.20
            combust = combustion.get(planet, {}).get("is_combust", False)
            if combust:
                score -= 18
            if data.get("retrograde"):
                score += 5
            score = round(max(0, min(100, score)), 2)
            strengths[planet] = {
                "score": score,
                "status": "strong" if score >= 75 else ("moderate" if score >= 50 else "weak"),
                "house": house,
                "dignity": dign["status"],
                "house_strength": house_score,
                "avastha": avasthas.get(planet),
                "combust": combust,
                "retrograde": bool(data.get("retrograde", False)),
            }
        return strengths

    def _house_lords(self, lagna_sign: int, planets: dict[str, Any], strengths: dict[str, Any]) -> list[dict[str, Any]]:
        lords = []
        for house in range(1, 13):
            sign_number = ((lagna_sign + house - 2) % 12) + 1
            lord = SIGN_LORD[sign_number]
            lord_house = house_from_lagna(int(planets[lord]["sign_number"]), lagna_sign)
            lords.append(
                {
                    "house": house,
                    "sign": sign_name(sign_number),
                    "lord": lord,
                    "lord_placed_house": lord_house,
                    "lord_strength": strengths[lord]["score"],
                    "assessment": self._house_lord_assessment(house, lord_house, strengths[lord]["score"]),
                }
            )
        return lords

    def _house_lord_assessment(self, house: int, lord_house: int, score: float) -> str:
        if house == 7 and score >= 70 and lord_house not in DUSTHANA_HOUSES:
            return "supportive_for_marriage"
        if lord_house in DUSTHANA_HOUSES and score < 60:
            return "needs_attention"
        if lord_house in KENDRA_HOUSES | TRIKONA_HOUSES:
            return "supportive"
        return "neutral"

    def _yogas(self, lagna_sign: int, planets: dict[str, Any], strengths: dict[str, Any]) -> list[dict[str, Any]]:
        yogas = []
        moon_sign = int(planets["Moon"]["sign_number"])
        jupiter_house_from_moon = sign_distance(moon_sign, int(planets["Jupiter"]["sign_number"]))
        if jupiter_house_from_moon in KENDRA_HOUSES:
            yogas.append({"name": "Gaja Kesari Yoga", "present": True, "strength": strengths["Jupiter"]["score"]})
        for planet in ("Mars", "Mercury", "Jupiter", "Venus", "Saturn"):
            house = strengths[planet]["house"]
            sign_number = int(planets[planet]["sign_number"])
            if house in KENDRA_HOUSES and (sign_number in OWN_SIGNS[planet] or EXALTATION_SIGNS[planet] == sign_number):
                yogas.append({"name": f"{planet} Mahapurusha Yoga", "present": True, "strength": strengths[planet]["score"]})
        seventh_lord = SIGN_LORD[((lagna_sign + 7 - 2) % 12) + 1]
        if strengths[seventh_lord]["score"] >= 70:
            yogas.append({"name": "Strong Seventh Lord", "present": True, "strength": strengths[seventh_lord]["score"]})
        for planet, data in planets.items():
            sign_number = int(data["sign_number"])
            if DEBILITATION_SIGNS.get(planet) == sign_number:
                yogas.append({"name": f"{planet} debilitation", "present": True, "strength": strengths[planet]["score"]})
        return yogas

    def _summary_score(self, strengths: dict[str, Any], yogas: list[dict[str, Any]]) -> float:
        key_planets = ("Venus", "Jupiter", "Moon", "Mars", "Saturn")
        base = sum(float(strengths[planet]["score"]) for planet in key_planets) / len(key_planets)
        yoga_bonus = min(12.0, sum(float(yoga.get("strength", 0)) for yoga in yogas if "Yoga" in yoga["name"]) / 100.0 * 4)
        return round(max(0.0, min(100.0, base + yoga_bonus)), 2)
