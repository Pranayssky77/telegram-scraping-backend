from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from time import monotonic
from typing import Any

import httpx

from backend.models.schemas import PersonDetails
from backend.utils.config import Settings

logger = logging.getLogger(__name__)


class ProkeralaClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._access_token: str | None = None
        self._token_expires_at = 0.0
        self._token_lock = asyncio.Lock()
        self._request_lock = asyncio.Lock()
        self._last_request_at = 0.0

    async def _token(self) -> str:
        if not self.settings.prokerala_client_id or not self.settings.prokerala_client_secret:
            raise RuntimeError("Prokerala credentials are not configured")
        if self._access_token and monotonic() < self._token_expires_at:
            return self._access_token
        async with self._token_lock:
            if self._access_token and monotonic() < self._token_expires_at:
                return self._access_token
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    self.settings.prokerala_token_url,
                    data={"grant_type": "client_credentials"},
                    auth=(self.settings.prokerala_client_id, self.settings.prokerala_client_secret),
                )
                response.raise_for_status()
                data = response.json()
                self._access_token = data["access_token"]
                expires_in = ProkeralaClient._numeric_score(data.get("expires_in")) or 3600
                self._token_expires_at = monotonic() + max(expires_in - 60, 60)
                return self._access_token

    @staticmethod
    def _payload_person(prefix: str, person: PersonDetails) -> dict[str, Any]:
        dt = datetime.combine(person.dob, person.tob).replace(
            tzinfo=timezone(timedelta(hours=person.timezone))
        )
        return {
            f"{prefix}_dob": dt.isoformat(),
            f"{prefix}_coordinates": f"{person.latitude},{person.longitude}",
        }

    async def score(self, source: PersonDetails, candidate: PersonDetails) -> tuple[float | None, str]:
        try:
            payload: dict[str, Any] = {}
            payload.update({"ayanamsa": 1, "la": "en"})
            payload.update(self._payload_person("boy", source if source.gender == "Male" else candidate))
            payload.update(self._payload_person("girl", source if source.gender == "Female" else candidate))

            async with httpx.AsyncClient(timeout=30) as client:
                last_error = ""
                for attempt in range(self.settings.prokerala_max_retries):
                    token = await self._token()
                    await self._pace_request()
                    response = await client.get(
                        self.settings.prokerala_match_url,
                        params=payload,
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    if response.status_code == 401 and attempt == 0:
                        self._clear_token()
                        last_error = response.text
                        continue
                    if response.status_code == 429:
                        last_error = response.text
                        wait_seconds = self._retry_wait_seconds(response, attempt)
                        logger.info("Prokerala rate limit hit; retrying in %.1f seconds", wait_seconds)
                        await asyncio.sleep(wait_seconds)
                        continue
                    if response.status_code < 500:
                        response.raise_for_status()
                        data = response.json()
                        score = self._extract_score(data)
                        return score, "OK" if score is not None else "No score field found in Prokerala response"
                    last_error = response.text
                    await asyncio.sleep(self._retry_wait_seconds(response, attempt))
                return None, f"Prokerala retry limit reached after rate-limit/backoff retries: {last_error}"
        except Exception as exc:
            logger.warning("Prokerala score failed: %s", exc)
            return None, f"Prokerala error: {exc}"

    async def _pace_request(self) -> None:
        async with self._request_lock:
            elapsed = monotonic() - self._last_request_at
            wait_seconds = self.settings.prokerala_request_delay_seconds - elapsed
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
            self._last_request_at = monotonic()

    def _clear_token(self) -> None:
        self._access_token = None
        self._token_expires_at = 0.0

    def _retry_wait_seconds(self, response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            retry_seconds = self._parse_retry_after(retry_after)
            if retry_seconds is not None:
                return min(retry_seconds, 120.0)
        backoff = self.settings.prokerala_retry_base_seconds * (2**attempt)
        return min(backoff, 120.0)

    @staticmethod
    def _parse_retry_after(value: str) -> float | None:
        try:
            seconds = float(value)
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(value)
            except (TypeError, ValueError):
                return None
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            seconds = (retry_at - datetime.now(timezone.utc)).total_seconds()
        return max(seconds, 0.0)

    @staticmethod
    def _extract_score(data: Any) -> float | None:
        score = ProkeralaClient._guna_percentage(data)
        if score is not None:
            return score
        if isinstance(data, dict):
            for key in (
                "compatibility_score",
                "compatibilityScore",
                "score",
                "Score",
                "percentage",
                "Percentage",
                "total_score",
                "totalScore",
            ):
                score = ProkeralaClient._numeric_score(data.get(key))
                if score is not None:
                    return score
            for nested in data.values():
                score = ProkeralaClient._extract_score(nested)
                if score is not None:
                    return score
        if isinstance(data, list):
            for nested in data:
                score = ProkeralaClient._extract_score(nested)
                if score is not None:
                    return score
        return None

    @staticmethod
    def _guna_percentage(data: Any) -> float | None:
        if isinstance(data, dict):
            total = ProkeralaClient._numeric_score(
                ProkeralaClient._first_present(
                    data,
                    ("total_points", "obtained_points", "obtainedPoints", "total"),
                )
            )
            maximum = ProkeralaClient._numeric_score(
                ProkeralaClient._first_present(
                    data,
                    ("maximum_points", "maximumPoints", "max_points", "maxPoints", "maximum"),
                )
            )
            if total is not None and maximum:
                return round((total / maximum) * 100, 2)
            for nested in data.values():
                score = ProkeralaClient._guna_percentage(nested)
                if score is not None:
                    return score
        if isinstance(data, list):
            total_points = 0.0
            maximum_points = 0.0
            found_points = False
            for item in data:
                if not isinstance(item, dict):
                    continue
                obtained = ProkeralaClient._numeric_score(
                    ProkeralaClient._first_present(item, ("obtained_points", "obtainedPoints"))
                )
                maximum = ProkeralaClient._numeric_score(
                    ProkeralaClient._first_present(item, ("maximum_points", "maximumPoints"))
                )
                if obtained is not None and maximum:
                    total_points += obtained
                    maximum_points += maximum
                    found_points = True
            if found_points and maximum_points:
                return round((total_points / maximum_points) * 100, 2)
            for item in data:
                score = ProkeralaClient._guna_percentage(item)
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
        return None

    @staticmethod
    def _first_present(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
        for key in keys:
            if key in data and data[key] is not None:
                return data[key]
        return None
