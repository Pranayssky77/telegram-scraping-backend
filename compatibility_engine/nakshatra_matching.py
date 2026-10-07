from __future__ import annotations

import re
import unicodedata
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from backend.utils.constants import NAKSHATRAS

NAKSHATRA_INDEX = {name: index + 1 for index, name in enumerate(NAKSHATRAS)}

ALIASES = {
    "aswini": "Ashwini",
    "ashwini": "Ashwini",
    "bharani": "Bharani",
    "barani": "Bharani",
    "krittika": "Krittika",
    "kritika": "Krittika",
    "krithika": "Krittika",
    "kruthika": "Krittika",
    "kartika": "Krittika",
    "rohini": "Rohini",
    "mrigashira": "Mrigashira",
    "mrigasira": "Mrigashira",
    "mrigasira": "Mrigashira",
    "mrugasira": "Mrigashira",
    "ardra": "Ardra",
    "arudra": "Ardra",
    "punarvasu": "Punarvasu",
    "pushya": "Pushya",
    "pushyami": "Pushya",
    "poosam": "Pushya",
    "ashlesha": "Ashlesha",
    "aslesha": "Ashlesha",
    "magha": "Magha",
    "makha": "Magha",
    "purva phalguni": "Purva Phalguni",
    "poorva phalguni": "Purva Phalguni",
    "pubba": "Purva Phalguni",
    "uttara phalguni": "Uttara Phalguni",
    "uthara phalguni": "Uttara Phalguni",
    "hasta": "Hasta",
    "hastha": "Hasta",
    "chitra": "Chitra",
    "chitta": "Chitra",
    "swati": "Swati",
    "swathi": "Swati",
    "vishakha": "Vishakha",
    "vishaka": "Vishakha",
    "visakha": "Vishakha",
    "visaka": "Vishakha",
    "anuradha": "Anuradha",
    "anuradha": "Anuradha",
    "jyeshta": "Jyeshta",
    "jyestha": "Jyeshta",
    "moola": "Mula",
    "mula": "Mula",
    "purva ashadha": "Purva Ashadha",
    "poorva ashadha": "Purva Ashadha",
    "purvashada": "Purva Ashadha",
    "poorvashada": "Purva Ashadha",
    "purvaashada": "Purva Ashadha",
    "uttara ashadha": "Uttara Ashadha",
    "uthara ashadha": "Uttara Ashadha",
    "uttarashada": "Uttara Ashadha",
    "uttaraashada": "Uttara Ashadha",
    "shravana": "Shravana",
    "sravana": "Shravana",
    "sravanam": "Shravana",
    "saravana": "Shravana",
    "sarvana": "Shravana",
    "dhanishta": "Dhanishta",
    "dhanista": "Dhanishta",
    "shatabhisha": "Shatabhisha",
    "satabhisha": "Shatabhisha",
    "sathabhisha": "Shatabhisha",
    "purva bhadrapada": "Purva Bhadrapada",
    "poorva bhadrapada": "Purva Bhadrapada",
    "purvabhadra": "Purva Bhadrapada",
    "purva bhadra": "Purva Bhadrapada",
    "uttara bhadrapada": "Uttara Bhadrapada",
    "uthara bhadrapada": "Uttara Bhadrapada",
    "uttarabhadra": "Uttara Bhadrapada",
    "uttara bhadra": "Uttara Bhadrapada",
    "revati": "Revati",
    "revathi": "Revati",
}

GANA = {
    "Ashwini": "Deva",
    "Bharani": "Manushya",
    "Krittika": "Rakshasa",
    "Rohini": "Manushya",
    "Mrigashira": "Deva",
    "Ardra": "Manushya",
    "Punarvasu": "Deva",
    "Pushya": "Deva",
    "Ashlesha": "Rakshasa",
    "Magha": "Rakshasa",
    "Purva Phalguni": "Manushya",
    "Uttara Phalguni": "Manushya",
    "Hasta": "Deva",
    "Chitra": "Rakshasa",
    "Swati": "Deva",
    "Vishakha": "Rakshasa",
    "Anuradha": "Deva",
    "Jyeshta": "Rakshasa",
    "Mula": "Rakshasa",
    "Purva Ashadha": "Manushya",
    "Uttara Ashadha": "Manushya",
    "Shravana": "Deva",
    "Dhanishta": "Rakshasa",
    "Shatabhisha": "Rakshasa",
    "Purva Bhadrapada": "Manushya",
    "Uttara Bhadrapada": "Manushya",
    "Revati": "Deva",
}

NADI = {
    "Ashwini": "Adi",
    "Bharani": "Madhya",
    "Krittika": "Antya",
    "Rohini": "Antya",
    "Mrigashira": "Madhya",
    "Ardra": "Adi",
    "Punarvasu": "Adi",
    "Pushya": "Madhya",
    "Ashlesha": "Antya",
    "Magha": "Antya",
    "Purva Phalguni": "Madhya",
    "Uttara Phalguni": "Adi",
    "Hasta": "Adi",
    "Chitra": "Madhya",
    "Swati": "Antya",
    "Vishakha": "Antya",
    "Anuradha": "Madhya",
    "Jyeshta": "Adi",
    "Mula": "Adi",
    "Purva Ashadha": "Madhya",
    "Uttara Ashadha": "Antya",
    "Shravana": "Antya",
    "Dhanishta": "Madhya",
    "Shatabhisha": "Adi",
    "Purva Bhadrapada": "Adi",
    "Uttara Bhadrapada": "Madhya",
    "Revati": "Antya",
}

YONI = {
    "Ashwini": "Horse",
    "Bharani": "Elephant",
    "Krittika": "Sheep",
    "Rohini": "Serpent",
    "Mrigashira": "Serpent",
    "Ardra": "Dog",
    "Punarvasu": "Cat",
    "Pushya": "Sheep",
    "Ashlesha": "Cat",
    "Magha": "Rat",
    "Purva Phalguni": "Rat",
    "Uttara Phalguni": "Cow",
    "Hasta": "Buffalo",
    "Chitra": "Tiger",
    "Swati": "Buffalo",
    "Vishakha": "Tiger",
    "Anuradha": "Deer",
    "Jyeshta": "Deer",
    "Mula": "Dog",
    "Purva Ashadha": "Monkey",
    "Uttara Ashadha": "Mongoose",
    "Shravana": "Monkey",
    "Dhanishta": "Lion",
    "Shatabhisha": "Horse",
    "Purva Bhadrapada": "Lion",
    "Uttara Bhadrapada": "Cow",
    "Revati": "Elephant",
}

YONI_ENEMIES = {
    frozenset(("Horse", "Buffalo")),
    frozenset(("Elephant", "Lion")),
    frozenset(("Sheep", "Monkey")),
    frozenset(("Serpent", "Mongoose")),
    frozenset(("Dog", "Deer")),
    frozenset(("Cat", "Rat")),
    frozenset(("Cow", "Tiger")),
}

RAJJU = {
    "Ashwini": "Pada",
    "Ashlesha": "Pada",
    "Magha": "Pada",
    "Jyeshta": "Pada",
    "Mula": "Pada",
    "Revati": "Pada",
    "Bharani": "Kati",
    "Pushya": "Kati",
    "Purva Phalguni": "Kati",
    "Anuradha": "Kati",
    "Purva Ashadha": "Kati",
    "Uttara Bhadrapada": "Kati",
    "Krittika": "Nabhi",
    "Punarvasu": "Nabhi",
    "Uttara Phalguni": "Nabhi",
    "Vishakha": "Nabhi",
    "Uttara Ashadha": "Nabhi",
    "Purva Bhadrapada": "Nabhi",
    "Rohini": "Kantha",
    "Ardra": "Kantha",
    "Hasta": "Kantha",
    "Swati": "Kantha",
    "Shravana": "Kantha",
    "Shatabhisha": "Kantha",
    "Mrigashira": "Shira",
    "Chitra": "Shira",
    "Dhanishta": "Shira",
}

VEDHA_PAIRS = {
    frozenset(("Ashwini", "Jyeshta")),
    frozenset(("Bharani", "Anuradha")),
    frozenset(("Krittika", "Vishakha")),
    frozenset(("Rohini", "Swati")),
    frozenset(("Mrigashira", "Dhanishta")),
    frozenset(("Ardra", "Shravana")),
    frozenset(("Punarvasu", "Uttara Ashadha")),
    frozenset(("Pushya", "Purva Ashadha")),
    frozenset(("Ashlesha", "Mula")),
    frozenset(("Magha", "Revati")),
    frozenset(("Purva Phalguni", "Uttara Bhadrapada")),
    frozenset(("Uttara Phalguni", "Purva Bhadrapada")),
    frozenset(("Hasta", "Shatabhisha")),
}

TARA_NAMES = {
    1: "Janma",
    2: "Sampat",
    3: "Vipat",
    4: "Kshema",
    5: "Pratyak",
    6: "Sadhana",
    7: "Naidhana",
    8: "Mitra",
    9: "Param Mitra",
}
TARA_GOOD_POSITIONS = {2, 4, 6, 8, 9}
TARA_BAD_POSITIONS = {1, 3, 5, 7}


@dataclass(frozen=True)
class NormalizedNakshatra:
    name: str | None
    number: int | None
    pada: int | None
    raw: str


def _plain_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = text.lower()
    text = re.sub(r"[,._\-()/]+", " ", text)
    text = re.sub(r"\b(?:padam|pada|paadam|padham|pad|charan|charana|quarter|qtr|st|nd|rd|th)\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


@lru_cache(maxsize=4096)
def normalize_nakshatra(value: str | None) -> NormalizedNakshatra:
    raw = str(value or "")
    text = _plain_text(raw)
    pada = _extract_pada(text)
    text_without_numbers = re.sub(r"\b[1-4]\b", " ", text)
    text_without_numbers = re.sub(r"\s+", " ", text_without_numbers).strip()

    candidates = [text_without_numbers, text]
    for candidate in candidates:
        if candidate in ALIASES:
            name = ALIASES[candidate]
            return NormalizedNakshatra(name, NAKSHATRA_INDEX[name], pada, raw)

    compact = re.sub(r"\s+", "", text_without_numbers)
    for alias, name in ALIASES.items():
        if compact == re.sub(r"\s+", "", alias):
            return NormalizedNakshatra(name, NAKSHATRA_INDEX[name], pada, raw)

    for alias, name in sorted(ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        alias_compact = re.sub(r"\s+", "", alias)
        if alias in text_without_numbers or alias_compact in compact:
            return NormalizedNakshatra(name, NAKSHATRA_INDEX[name], pada, raw)

    return NormalizedNakshatra(None, None, pada, raw)


def _extract_pada(text: str) -> int | None:
    match = re.search(r"\b([1-4])(?:st|nd|rd|th)?\b", text)
    return int(match.group(1)) if match else None


def _distance(from_number: int, to_number: int) -> int:
    return ((to_number - from_number) % 27) + 1


def _tara_remainder(distance: int) -> int:
    return distance % 9


def _tara_position(distance: int) -> int:
    remainder = _tara_remainder(distance)
    return 9 if remainder == 0 else remainder


def _tara_detail(from_number: int, to_number: int) -> dict[str, Any]:
    distance = _distance(from_number, to_number)
    position = _tara_position(distance)
    return {
        "distance": distance,
        "position": position,
        "name": TARA_NAMES[position],
        "favorable": position in TARA_GOOD_POSITIONS and position not in TARA_BAD_POSITIONS,
    }


def tara_koota_points(first_number: int, second_number: int) -> float:
    first_to_second = _tara_detail(first_number, second_number)
    second_to_first = _tara_detail(second_number, first_number)
    favorable_count = int(first_to_second["favorable"]) + int(second_to_first["favorable"])
    return favorable_count * 1.5


def _component(score: float, status: str, reason: str, severe: bool = False) -> dict[str, Any]:
    return {"score": score, "status": status, "reason": reason, "severe": severe}


class NakshatraMatcher:
    WEIGHTS = {
        "tara": 0.25,
        "dina": 0.10,
        "gana": 0.15,
        "nadi": 0.20,
        "yoni": 0.15,
        "rajju": 0.10,
        "vedha": 0.05,
    }

    @lru_cache(maxsize=20000)
    def score(self, boy_star: str | None, girl_star: str | None) -> dict[str, Any]:
        boy = normalize_nakshatra(boy_star)
        girl = normalize_nakshatra(girl_star)
        if boy.name is None or girl.name is None or boy.number is None or girl.number is None:
            return {
                "score": 50.0,
                "rejected": False,
                "severity": "unknown",
                "reason": "Nakshatra could not be normalized; retained as neutral",
                "boy_nakshatra": boy.name,
                "girl_nakshatra": girl.name,
                "boy_pada": boy.pada,
                "girl_pada": girl.pada,
                "components": {},
            }

        components = {
            "tara": self._tara(boy.number, girl.number),
            "dina": self._dina(boy.number, girl.number),
            "gana": self._gana(boy.name, girl.name),
            "nadi": self._nadi(boy.name, girl.name),
            "yoni": self._yoni(boy.name, girl.name),
            "rajju": self._rajju(boy.name, girl.name),
            "vedha": self._vedha(boy.name, girl.name),
        }
        score = round(sum(components[name]["score"] * weight for name, weight in self.WEIGHTS.items()), 2)
        severe_reasons = [component["reason"] for component in components.values() if component["severe"]]
        rejected = score < 45.0 or bool(severe_reasons)
        if severe_reasons:
            severity = "severe"
            reason = "; ".join(severe_reasons)
        elif score < 45.0:
            severity = "low"
            reason = "Nakshatra compatibility score is below threshold"
        elif score < 70.0:
            severity = "medium"
            reason = "Medium nakshatra compatibility"
        else:
            severity = "favorable"
            reason = "Favorable nakshatra compatibility"

        return {
            "score": score,
            "rejected": rejected,
            "severity": severity,
            "reason": reason,
            "boy_nakshatra": boy.name,
            "girl_nakshatra": girl.name,
            "boy_pada": boy.pada,
            "girl_pada": girl.pada,
            "tara_compatibility": components["tara"],
            "dina_compatibility": components["dina"],
            "gana_compatibility": components["gana"],
            "nadi_compatibility": components["nadi"],
            "yoni_compatibility": components["yoni"],
            "rajju_compatibility": components["rajju"],
            "vedha_compatibility": components["vedha"],
            "components": components,
        }

    def score_pairs(self, pairs: list[tuple[str | None, str | None]], processes: int = 1) -> list[dict[str, Any]]:
        if processes <= 1 or len(pairs) < 100:
            return [self.score(boy_star, girl_star) for boy_star, girl_star in pairs]
        with ProcessPoolExecutor(max_workers=processes) as executor:
            return list(executor.map(_score_pair_for_process, pairs))

    def _tara(self, boy_number: int, girl_number: int) -> dict[str, Any]:
        boy_to_girl = _tara_detail(boy_number, girl_number)
        girl_to_boy = _tara_detail(girl_number, boy_number)
        points = tara_koota_points(boy_number, girl_number)
        reason = (
            "Tara Koota "
            f"{points:g}/3: boy to girl {boy_to_girl['name']} "
            f"({boy_to_girl['position']}, count {boy_to_girl['distance']}), "
            f"girl to boy {girl_to_boy['name']} "
            f"({girl_to_boy['position']}, count {girl_to_boy['distance']})"
        )
        if points == 3.0:
            return _component(100.0, "favorable", reason)
        if points == 1.5:
            return _component(50.0, "medium", reason)
        return _component(0.0, "unfavorable", reason, True)

    def _dina(self, boy_number: int, girl_number: int) -> dict[str, Any]:
        detail = _tara_detail(girl_number, boy_number)
        reason = f"Dina Tara is {detail['name']} ({detail['position']}, count {detail['distance']})"
        if detail["favorable"]:
            return _component(100.0, "favorable", reason)
        return _component(25.0, "unfavorable", reason)

    def _gana(self, boy_name: str, girl_name: str) -> dict[str, Any]:
        boy_gana = GANA[boy_name]
        girl_gana = GANA[girl_name]
        if boy_gana == girl_gana:
            return _component(100.0, "favorable", f"Same gana: {boy_gana}")
        if "Rakshasa" in {boy_gana, girl_gana}:
            return _component(35.0, "unfavorable", f"Gana mismatch: {boy_gana}/{girl_gana}")
        return _component(70.0, "medium", f"Moderate gana match: {boy_gana}/{girl_gana}")

    def _nadi(self, boy_name: str, girl_name: str) -> dict[str, Any]:
        boy_nadi = NADI[boy_name]
        girl_nadi = NADI[girl_name]
        if boy_nadi == girl_nadi:
            return _component(0.0, "unfavorable", f"Severe Nadi dosha: both are {boy_nadi}", True)
        return _component(100.0, "favorable", f"Nadi differs: {boy_nadi}/{girl_nadi}")

    def _yoni(self, boy_name: str, girl_name: str) -> dict[str, Any]:
        boy_yoni = YONI[boy_name]
        girl_yoni = YONI[girl_name]
        if boy_yoni == girl_yoni:
            return _component(100.0, "favorable", f"Same yoni: {boy_yoni}")
        if frozenset((boy_yoni, girl_yoni)) in YONI_ENEMIES:
            return _component(20.0, "unfavorable", f"Yoni enemies: {boy_yoni}/{girl_yoni}")
        return _component(65.0, "medium", f"Neutral yoni relation: {boy_yoni}/{girl_yoni}")

    def _rajju(self, boy_name: str, girl_name: str) -> dict[str, Any]:
        boy_rajju = RAJJU[boy_name]
        girl_rajju = RAJJU[girl_name]
        if boy_rajju == girl_rajju:
            return _component(0.0, "unfavorable", f"Severe Rajju mismatch: both are {boy_rajju}", True)
        return _component(100.0, "favorable", f"Rajju differs: {boy_rajju}/{girl_rajju}")

    def _vedha(self, boy_name: str, girl_name: str) -> dict[str, Any]:
        if frozenset((boy_name, girl_name)) in VEDHA_PAIRS:
            return _component(0.0, "unfavorable", f"Severe Vedha incompatibility: {boy_name}/{girl_name}", True)
        return _component(100.0, "favorable", "No Vedha pair conflict")


def _score_pair_for_process(pair: tuple[str | None, str | None]) -> dict[str, Any]:
    return NakshatraMatcher().score(pair[0], pair[1])
