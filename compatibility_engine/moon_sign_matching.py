from __future__ import annotations


class MoonSignMatcher:
    def score(self, source_horoscope: dict, candidate_horoscope: dict) -> dict:
        a = int(source_horoscope["moon_sign_number"])
        b = int(candidate_horoscope["moon_sign_number"])
        distance = ((b - a) % 12) + 1
        reverse_distance = ((a - b) % 12) + 1
        difficult_pairs = {(2, 12), (6, 8), (5, 9)}
        if (distance, reverse_distance) in difficult_pairs or (reverse_distance, distance) in difficult_pairs:
            score = 35.0
        elif distance in {1, 3, 4, 7, 10, 11}:
            score = 85.0
        else:
            score = 60.0
        return {"score": score, "distance": distance, "reverse_distance": reverse_distance}

