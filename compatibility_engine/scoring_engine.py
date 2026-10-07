from __future__ import annotations

from backend.models.schemas import PersonDetails


class ScoringEngine:
    WEIGHTS = {
        "ashta_koota": 0.45,
        "nakshatra": 0.18,
        "dosha": 0.14,
        "dasha": 0.09,
        "education_age": 0.04,
        "advanced_chart": 0.10,
    }

    def education_age_score(self, source: PersonDetails, candidate: PersonDetails) -> float:
        age_gap = abs(source.age - candidate.age)
        age_score = max(0.0, 100.0 - age_gap * 8.0)
        education_bonus = 100.0 if candidate.education else 70.0
        return round((age_score * 0.7) + (education_bonus * 0.3), 2)

    def final_score(
        self,
        ashta_koota_percentage: float,
        nakshatra_score: float,
        dosha_score: float,
        dasha_score: float,
        education_age_score: float,
        advanced_chart_score: float | None = None,
    ) -> float:
        advanced_chart_score = education_age_score if advanced_chart_score is None else advanced_chart_score
        score = (
            ashta_koota_percentage * self.WEIGHTS["ashta_koota"]
            + nakshatra_score * self.WEIGHTS["nakshatra"]
            + dosha_score * self.WEIGHTS["dosha"]
            + dasha_score * self.WEIGHTS["dasha"]
            + education_age_score * self.WEIGHTS["education_age"]
            + advanced_chart_score * self.WEIGHTS["advanced_chart"]
        )
        return round(max(0.0, min(100.0, score)), 2)
