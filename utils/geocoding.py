from __future__ import annotations

import asyncio
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import httpx


class GeocodingService:
    def __init__(self) -> None:
        self.nominatim_url = "https://nominatim.openstreetmap.org/search"
        self.open_meteo_url = "https://geocoding-api.open-meteo.com/v1/search"
        self.open_meteo_forecast_url = "https://api.open-meteo.com/v1/forecast"
        self.user_agent = "telegram-scraping-astro-matching/1.0"

    async def search_places(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        query = query.strip()
        if len(query) < 2:
            return []

        async with httpx.AsyncClient(timeout=15, headers={"User-Agent": self.user_agent}) as client:
            for variant in self._query_variants(query):
                try:
                    places = await self._search_nominatim(client, variant, limit)
                except httpx.HTTPError:
                    continue
                if places:
                    return places
            for variant in self._query_variants(query):
                try:
                    places = await self._search_open_meteo(client, variant, limit)
                except httpx.HTTPError:
                    continue
                if places:
                    return places
        return []

    async def _search_nominatim(self, client: httpx.AsyncClient, query: str, limit: int) -> list[dict[str, Any]]:
        response = await client.get(
            self.nominatim_url,
            params={
                "q": query,
                "format": "jsonv2",
                "addressdetails": 1,
                "namedetails": 1,
                "limit": max(1, min(limit, 10)),
                "accept-language": "en",
            },
        )
        response.raise_for_status()
        places = self._places_from_nominatim(response.json())
        await self._attach_timezones(client, places)
        return places

    async def _search_open_meteo(self, client: httpx.AsyncClient, query: str, limit: int) -> list[dict[str, Any]]:
        response = await client.get(
            self.open_meteo_url,
            params={
                "name": query,
                "count": max(1, min(limit, 10)),
                "language": "en",
            },
        )
        response.raise_for_status()
        return self._places_from_open_meteo(response.json().get("results", []))

    async def timezone_name(self, latitude: float, longitude: float) -> str | None:
        async with httpx.AsyncClient(timeout=15, headers={"User-Agent": self.user_agent}) as client:
            return await self._timezone_for_coordinates(client, latitude, longitude)

    async def _attach_timezones(self, client: httpx.AsyncClient, places: list[dict[str, Any]]) -> None:
        timezones = await asyncio.gather(
            *(self._timezone_for_coordinates(client, place["latitude"], place["longitude"]) for place in places),
            return_exceptions=True,
        )
        for place, timezone in zip(places, timezones):
            if isinstance(timezone, str):
                place["timezone"] = timezone

    async def _timezone_for_coordinates(self, client: httpx.AsyncClient, latitude: float, longitude: float) -> str | None:
        response = await client.get(
            self.open_meteo_forecast_url,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "forecast_days": 1,
                "timezone": "auto",
            },
        )
        response.raise_for_status()
        timezone = response.json().get("timezone")
        return timezone if isinstance(timezone, str) and timezone else None

    @staticmethod
    def _query_variants(query: str) -> list[str]:
        variants = [query]
        if query.lower().endswith("a"):
            variants.append(query[:-1])
        for index, character in enumerate(query):
            next_character = query[index + 1 : index + 2].lower()
            if character.lower() in {"t", "d"} and next_character != "h":
                variants.append(f"{query[: index + 1]}h{query[index + 1 :]}")
        return list(dict.fromkeys(variants))

    @staticmethod
    def _places_from_nominatim(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        places: list[dict[str, Any]] = []
        seen: set[tuple[str, float, float]] = set()
        for item in results:
            address = item.get("address") or {}
            name_details = item.get("namedetails") or {}
            place_name = (
                name_details.get("name:en")
                or name_details.get("name")
                or item.get("name")
                or address.get("village")
                or address.get("town")
                or address.get("city")
                or item.get("display_name", "").split(",", 1)[0]
            )
            latitude = float(item["lat"])
            longitude = float(item["lon"])
            key = (str(place_name).lower(), round(latitude, 5), round(longitude, 5))
            if key in seen:
                continue
            seen.add(key)
            places.append(
                {
                    "place": place_name,
                    "latitude": latitude,
                    "longitude": longitude,
                    "mandal": address.get("county") or address.get("municipality") or address.get("suburb"),
                    "district": address.get("state_district") or address.get("district") or address.get("county"),
                    "state": address.get("state") or address.get("region"),
                    "country": address.get("country"),
                    "timezone": None,
                }
            )
        return places

    @staticmethod
    def _places_from_open_meteo(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        places: list[dict[str, Any]] = []
        for item in results:
            places.append(
                {
                    "place": item.get("name", ""),
                    "latitude": float(item["latitude"]),
                    "longitude": float(item["longitude"]),
                    "mandal": item.get("admin3") or item.get("admin4"),
                    "district": item.get("admin2"),
                    "state": item.get("admin1"),
                    "country": item.get("country"),
                    "timezone": item.get("timezone"),
                }
            )
        return places


def timezone_offset(timezone_name: str, dob: date, tob: time) -> float:
    offset = datetime.combine(dob, tob, tzinfo=ZoneInfo(timezone_name)).utcoffset()
    if offset is None:
        raise ValueError(f"Could not calculate timezone offset for {timezone_name}.")
    return offset.total_seconds() / 3600
