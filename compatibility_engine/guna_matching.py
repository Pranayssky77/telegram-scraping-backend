from __future__ import annotations

from backend.compatibility_engine.nakshatra_matching import GANA, NADI, YONI, tara_koota_points
from backend.utils.constants import NAKSHATRAS

VARNA_BY_SIGN = {
    1: "Kshatriya", 2: "Vaishya", 3: "Shudra", 4: "Brahmin",
    5: "Kshatriya", 6: "Vaishya", 7: "Shudra", 8: "Brahmin",
    9: "Kshatriya", 10: "Vaishya", 11: "Shudra", 12: "Brahmin",
}
VARNA_RANK = {"Shudra": 1, "Vaishya": 2, "Kshatriya": 3, "Brahmin": 4}
VASHYA_BY_SIGN = {
    1: "Chatushpada", 2: "Chatushpada", 3: "Nara", 4: "Jalachara",
    5: "Vanachara", 6: "Nara", 7: "Nara", 8: "Keeta",
    9: "Chatushpada", 10: "Jalachara", 11: "Nara", 12: "Jalachara",
}
PLANET_FRIENDS = {
    "Sun": {"Moon", "Mars", "Jupiter"},
    "Moon": {"Sun", "Mercury"},
    "Mars": {"Sun", "Moon", "Jupiter"},
    "Mercury": {"Sun", "Venus"},
    "Jupiter": {"Sun", "Moon", "Mars"},
    "Venus": {"Mercury", "Saturn"},
    "Saturn": {"Mercury", "Venus"},
}
SIGN_LORD = {
    1: "Mars", 2: "Venus", 3: "Mercury", 4: "Moon", 5: "Sun", 6: "Mercury",
    7: "Venus", 8: "Mars", 9: "Jupiter", 10: "Saturn", 11: "Saturn", 12: "Jupiter",
}


def _tara_score(a_star: int, b_star: int) -> float:
    return tara_koota_points(a_star, b_star)


def _bhakoot_score(a_sign: int, b_sign: int) -> float:
    pair = (((b_sign - a_sign) % 12) + 1, ((a_sign - b_sign) % 12) + 1)
    if pair in {(2, 12), (12, 2), (5, 9), (9, 5), (6, 8), (8, 6)}:
        return 0.0
    return 7.0


class GunaMatcher:
    def match(self, source_horoscope: dict, candidate_horoscope: dict) -> dict:
        a_sign = int(source_horoscope["moon_sign_number"])
        b_sign = int(candidate_horoscope["moon_sign_number"])
        a_star = int(source_horoscope["moon_nakshatra_number"])
        b_star = int(candidate_horoscope["moon_nakshatra_number"])

        a_varna = VARNA_BY_SIGN[a_sign]
        b_varna = VARNA_BY_SIGN[b_sign]
        varna = 1.0 if VARNA_RANK[b_varna] >= VARNA_RANK[a_varna] else 0.0

        vashya = 2.0 if VASHYA_BY_SIGN[a_sign] == VASHYA_BY_SIGN[b_sign] else 1.0
        tara = _tara_score(a_star, b_star)
        a_nakshatra = NAKSHATRAS[a_star - 1]
        b_nakshatra = NAKSHATRAS[b_star - 1]
        yoni = 4.0 if YONI[a_nakshatra] == YONI[b_nakshatra] else 2.0

        a_lord = SIGN_LORD[a_sign]
        b_lord = SIGN_LORD[b_sign]
        if a_lord == b_lord:
            graha = 5.0
        elif b_lord in PLANET_FRIENDS.get(a_lord, set()) or a_lord in PLANET_FRIENDS.get(b_lord, set()):
            graha = 4.0
        else:
            graha = 2.0

        a_gana = GANA[a_nakshatra]
        b_gana = GANA[b_nakshatra]
        gana = 6.0 if a_gana == b_gana else (3.0 if "Rakshasa" not in {a_gana, b_gana} else 1.0)
        bhakoot = _bhakoot_score(a_sign, b_sign)
        nadi = 8.0 if NADI[a_nakshatra] != NADI[b_nakshatra] else 0.0

        breakdown = {
            "Varna": varna,
            "Vashya": vashya,
            "Tara": tara,
            "Yoni": yoni,
            "Graha Maitri": graha,
            "Gana": gana,
            "Bhakoot": bhakoot,
            "Nadi": nadi,
        }
        total = round(sum(breakdown.values()), 2)
        return {
            "gunas": total,
            "percentage": round((total / 36.0) * 100.0, 2),
            "breakdown": breakdown,
            "source_nakshatra": NAKSHATRAS[a_star - 1],
            "candidate_nakshatra": NAKSHATRAS[b_star - 1],
        }
