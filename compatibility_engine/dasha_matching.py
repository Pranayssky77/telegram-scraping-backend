from __future__ import annotations

FRIENDLY_LORDS = {
    "Sun": {"Moon", "Mars", "Jupiter"},
    "Moon": {"Sun", "Mercury"},
    "Mars": {"Sun", "Moon", "Jupiter"},
    "Mercury": {"Sun", "Venus"},
    "Jupiter": {"Sun", "Moon", "Mars"},
    "Venus": {"Mercury", "Saturn"},
    "Saturn": {"Mercury", "Venus"},
    "Rahu": {"Venus", "Saturn", "Mercury"},
    "Ketu": {"Mars", "Jupiter", "Sun"},
}


class DashaMatcher:
    def score(self, source_dasha: dict, candidate_dasha: dict) -> dict:
        source_lord = source_dasha["mahadasha_lord"]
        candidate_lord = candidate_dasha["mahadasha_lord"]
        source_antar = source_dasha["antardasha_lord"]
        candidate_antar = candidate_dasha["antardasha_lord"]

        score = 50.0
        if source_lord == candidate_lord:
            score += 25
        elif candidate_lord in FRIENDLY_LORDS.get(source_lord, set()):
            score += 20
        if source_antar == candidate_antar:
            score += 15
        elif candidate_antar in FRIENDLY_LORDS.get(source_antar, set()):
            score += 10
        return {"score": min(100.0, score), "reason": f"{source_lord}/{source_antar} vs {candidate_lord}/{candidate_antar}"}

