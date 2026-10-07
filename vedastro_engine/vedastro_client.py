from __future__ import annotations

import json
import logging
import math
from typing import Any

from backend.models.schemas import PersonDetails
from backend.utils.config import Settings

logger = logging.getLogger(__name__)


class VedAstroClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def score(self, source: PersonDetails, candidate: PersonDetails) -> tuple[float | None, str]:
        try:
            from vedastro import Calculate
        except Exception as exc:
            logger.warning("VedAstro package unavailable: %s", exc)
            return None, f"VedAstro unavailable: {exc}"

        try:
            Calculate.SetAPIKey(self.settings.vedastro_api_key)
            match_report = Calculate.MatchReport(
                self._birth_time(source if source.gender == "Male" else candidate),
                self._birth_time(source if source.gender == "Female" else candidate),
            )
            score = self._extract_score(match_report)
            if score is None:
                return None, "No score field found in VedAstro MatchReport response"
            return score, "OK"
        except Exception as exc:
            logger.warning("VedAstro score failed: %s", exc)
            return None, f"VedAstro error: {exc}"

    @staticmethod
    def _birth_time(person: PersonDetails) -> Any:
        from vedastro import GeoLocation, Time

        return Time(
            hour=person.tob.hour,
            minute=person.tob.minute,
            day=person.dob.day,
            month=person.dob.month,
            year=person.dob.year,
            offset=VedAstroClient._offset(person.timezone),
            geolocation=GeoLocation(person.pob, person.longitude, person.latitude),
        )

    @staticmethod
    def _offset(hours: float) -> str:
        sign = "+" if hours >= 0 else "-"
        total_minutes = round(abs(hours) * 60)
        offset_hours, offset_minutes = divmod(total_minutes, 60)
        return f"{sign}{offset_hours:02d}:{offset_minutes:02d}"

    @classmethod
    def _extract_score(cls, value: Any) -> float | None:
        direct_score = cls._numeric_score(value)
        if direct_score is not None:
            return direct_score
        if isinstance(value, str):
            try:
                return cls._extract_score(json.loads(value))
            except json.JSONDecodeError:
                return None
        if hasattr(value, "model_dump"):
            return cls._extract_score(value.model_dump())
        if hasattr(value, "to_dict"):
            return cls._extract_score(value.to_dict())
        if hasattr(value, "__dict__") and not isinstance(value, type):
            return cls._extract_score(vars(value))
        if isinstance(value, dict):
            for key in (
                "KutaScore",
                "kutaScore",
                "CompatibilityScore",
                "compatibilityScore",
                "Score",
                "score",
                "Total",
                "total",
                "Percentage",
                "percentage",
            ):
                score = cls._numeric_score(value.get(key))
                if score is not None:
                    return score
            for nested in value.values():
                score = cls._extract_score(nested)
                if score is not None:
                    return score
        if isinstance(value, list):
            for nested in value:
                score = cls._extract_score(nested)
                if score is not None:
                    return score
        return None

    @staticmethod
    def _numeric_score(value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            return round(float(value), 2)
        if isinstance(value, str):
            try:
                number = float(value.strip())
            except ValueError:
                return None
            if math.isfinite(number):
                return round(number, 2)
        if isinstance(value, dict):
            for key in ("Score", "score", "Total", "total", "Value", "value"):
                nested = value.get(key)
                score = VedAstroClient._numeric_score(nested)
                if score is not None:
                    return score
        return None
