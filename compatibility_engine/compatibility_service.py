from __future__ import annotations

import asyncio
import logging
from typing import Any

import pandas as pd

from backend.compatibility_engine.dasha_matching import DashaMatcher
from backend.compatibility_engine.dosha_matching import DoshaMatcher
from backend.compatibility_engine.guna_matching import GunaMatcher
from backend.compatibility_engine.nakshatra_matching import NakshatraMatcher
from backend.compatibility_engine.scoring_engine import ScoringEngine
from backend.models.schemas import PersonDetails
from backend.prokerala_engine.prokerala_client import ProkeralaClient
from backend.swiss_engine.dasha_calculator import DashaCalculator
from backend.swiss_engine.dosha_calculator import DoshaCalculator
from backend.swiss_engine.horoscope_generator import HoroscopeGenerator
from backend.vedastro_engine.vedastro_client import VedAstroClient

logger = logging.getLogger(__name__)


class CompatibilityService:
    def __init__(self, prokerala: ProkeralaClient, vedastro: VedAstroClient) -> None:
        self.prokerala = prokerala
        self.vedastro = vedastro
        self.horoscope = HoroscopeGenerator()
        self.guna = GunaMatcher()
        self.nakshatra = NakshatraMatcher()
        self.dosha_calc = DoshaCalculator()
        self.dosha = DoshaMatcher()
        self.dasha_calc = DashaCalculator()
        self.dasha = DashaMatcher()
        self.scoring = ScoringEngine()

    async def _score_candidate(
        self,
        source: PersonDetails,
        candidate: PersonDetails,
        source_horoscope: dict[str, Any],
        source_dosha: Any,
        source_dasha: Any,
    ) -> dict[str, Any]:
        candidate_horoscope = self.horoscope.generate(candidate)
        guna = self.guna.match(source_horoscope, candidate_horoscope)
        source_star = str(source_horoscope["moon_nakshatra"])
        candidate_star = str(candidate_horoscope["moon_nakshatra"])
        boy_star = source_star if source.gender == "Male" else candidate_star
        girl_star = source_star if source.gender == "Female" else candidate_star
        nakshatra = self.nakshatra.score(boy_star, girl_star)
        candidate_dosha = self.dosha_calc.kuja_dosha(candidate_horoscope)
        dosha = self.dosha.score(source_dosha, candidate_dosha)
        candidate_dasha = self.dasha_calc.vimshottari_at_birth(candidate_horoscope)
        dasha = self.dasha.score(source_dasha, candidate_dasha)
        education_age = self.scoring.education_age_score(source, candidate)
        advanced_chart = self._advanced_chart_score(source_horoscope, candidate_horoscope)
        our_score = self.scoring.final_score(
            guna["percentage"],
            nakshatra["score"],
            dosha["score"],
            dasha["score"],
            education_age,
            advanced_chart["score"],
        )

        loop = asyncio.get_event_loop()

        async def _vedastro() -> tuple:
            fut = loop.run_in_executor(None, self.vedastro.score, source, candidate)
            try:
                return await asyncio.wait_for(asyncio.shield(fut), timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                return None, "VedAstro timed out"

        (prokerala_score, prokerala_note), (vedastro_score, vedastro_note) = await asyncio.gather(
            self.prokerala.score(source, candidate),
            _vedastro(),
        )
        available_scores = [s for s in (prokerala_score, vedastro_score, our_score) if s is not None]
        average = round(sum(available_scores) / len(available_scores), 2)
        best_window = self._best_marriage_window(candidate_horoscope)

        return {
            "Id": candidate.row_id,
            "Name": candidate.name,
            "Gender": candidate.gender,
            "Age": candidate.age,
            "DOB": candidate.dob.isoformat(),
            "Star": candidate.star or candidate_horoscope["moon_nakshatra"],
            "Nakshathra": nakshatra.get("girl_nakshatra") or candidate.star or candidate_horoscope["moon_nakshatra"],
            "Gothram": candidate.gotram,
            "Education": candidate.education,
            "Study": candidate.education,
            "Job": candidate.job,
            "Contact": candidate.contact,
            "Prokerala Score": prokerala_score,
            "VedAstro Score": vedastro_score,
            "Our Model Score": our_score,
            "Advanced Chart Score": advanced_chart["score"],
            "Best Marriage Window": best_window,
            "Average Score": average,
            "Notes": {
                "prokerala": prokerala_note,
                "vedastro": vedastro_note,
                "guna": guna,
                "nakshatra": nakshatra,
                "dosha": dosha,
                "dasha": dasha,
                "education_age": {"score": education_age},
                "advanced_chart": advanced_chart,
                "source_chart_analysis": source_horoscope.get("analysis", {}),
                "candidate_chart_analysis": candidate_horoscope.get("analysis", {}),
                "candidate_marriage_timing": candidate_horoscope.get("marriage_timing", {}),
                "source_dosha": source_dosha,
                "candidate_dosha": candidate_dosha,
            },
        }

    def _best_marriage_window(self, horoscope: dict[str, Any]) -> str | None:
        windows = horoscope.get("marriage_timing", {}).get("windows", [])
        if not windows:
            return None
        best = max(windows, key=lambda item: float(item.get("average_score", 0.0)))
        return f"{best['from_year']}-{best['to_year']} ({best['grade']})"

    def _advanced_chart_score(
        self,
        source_horoscope: dict[str, Any],
        candidate_horoscope: dict[str, Any],
    ) -> dict[str, Any]:
        source_analysis = source_horoscope.get("analysis", {})
        candidate_analysis = candidate_horoscope.get("analysis", {})
        source_score = float(source_analysis.get("summary_score", 60.0))
        candidate_score = float(candidate_analysis.get("summary_score", 60.0))
        candidate_timing = candidate_horoscope.get("marriage_timing", {})
        best_years = candidate_timing.get("best_years", [])
        timing_score = max((float(item.get("score", 0.0)) for item in best_years), default=60.0)
        score = round((source_score * 0.35) + (candidate_score * 0.45) + (timing_score * 0.20), 2)
        return {
            "score": score,
            "source_chart_score": source_score,
            "candidate_chart_score": candidate_score,
            "candidate_best_timing_score": timing_score,
            "reason": "Blend of planet strength, house/yoga analysis, and candidate marriage timing",
        }

    async def generate(self, source: PersonDetails, candidates: list[PersonDetails]) -> pd.DataFrame:
        source_horoscope = self.horoscope.generate(source)
        source_dosha = self.dosha_calc.kuja_dosha(source_horoscope)
        source_dasha = self.dasha_calc.vimshottari_at_birth(source_horoscope)

        rows: list[dict[str, Any]] = await asyncio.gather(*(
            self._score_candidate(source, candidate, source_horoscope, source_dosha, source_dasha)
            for candidate in candidates
        ))

        result = pd.DataFrame(rows)
        if result.empty:
            return result
        result = result.sort_values("Average Score", ascending=False).reset_index(drop=True)
        result["Rank"] = range(1, len(result) + 1)
        return result[
            [
                "Id",
                "Name",
                "Gender",
                "Age",
                "DOB",
                "Star",
                "Nakshathra",
                "Gothram",
                "Education",
                "Study",
                "Job",
                "Contact",
                "Prokerala Score",
                "VedAstro Score",
                "Our Model Score",
                "Advanced Chart Score",
                "Best Marriage Window",
                "Average Score",
                "Rank",
                "Notes",
            ]
        ]
