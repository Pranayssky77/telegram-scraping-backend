from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


def age_from_dob(value: date) -> int:
    today = date.today()
    return today.year - value.year - ((today.month, today.day) < (value.month, value.day))


class PersonDetails(BaseModel):
    row_id: int | str | None = Field(default=None, alias="Id")
    name: str = Field(..., alias="Name")
    gender: str = Field(..., alias="Gender")
    age: int = Field(..., alias="Age", ge=0, le=120)
    dob: date = Field(..., alias="DOB")
    tob: time = Field(..., alias="TOB")
    pob: str = Field(..., alias="POB")
    latitude: float = Field(..., alias="Latitude", ge=-90, le=90)
    longitude: float = Field(..., alias="Longitude", ge=-180, le=180)
    timezone: float = Field(..., alias="Timezone")
    star: str | None = Field(default=None, alias="Star")
    gotram: str | None = Field(default=None, alias="Gotram")
    education: str | None = Field(default=None, alias="Education")
    job: str | None = Field(default=None, alias="Job")
    contact: str | None = Field(default=None, alias="Contact")

    model_config = {"populate_by_name": True}

    @model_validator(mode="before")
    @classmethod
    def normalize_input(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        if "Star" not in normalized:
            for key in ("Nakshathra", "Nakshatra"):
                if key in normalized:
                    normalized["Star"] = normalized[key]
                    break
        if "Gotram" not in normalized and "Gothram" in normalized:
            normalized["Gotram"] = normalized["Gothram"]
        if normalized.get("Age") in (None, "") and normalized.get("DOB"):
            dob = normalized["DOB"]
            if isinstance(dob, datetime):
                normalized["Age"] = age_from_dob(dob.date())
            elif isinstance(dob, date):
                normalized["Age"] = age_from_dob(dob)
            else:
                normalized["Age"] = age_from_dob(date.fromisoformat(str(dob).strip()))
        return normalized

    @field_validator("gender")
    @classmethod
    def normalize_gender(cls, value: str) -> str:
        value = value.strip().title()
        if value not in {"Male", "Female"}:
            raise ValueError("Gender must be Male or Female")
        return value


class FilteredUser(PersonDetails):
    pass


class CompatibilityResult(BaseModel):
    name: str = Field(..., alias="Name")
    gender: str = Field(..., alias="Gender")
    age: int = Field(..., alias="Age")
    dob: date = Field(..., alias="DOB")
    star: str | None = Field(default=None, alias="Star")
    nakshathra: str | None = Field(default=None, alias="Nakshathra")
    gothram: str | None = Field(default=None, alias="Gothram")
    education: str | None = Field(default=None, alias="Education")
    study: str | None = Field(default=None, alias="Study")
    job: str | None = Field(default=None, alias="Job")
    contact: str | None = Field(default=None, alias="Contact")
    prokerala_score: float | None = Field(..., alias="Prokerala Score")
    vedastro_score: float | None = Field(..., alias="VedAstro Score")
    our_model_score: float = Field(..., alias="Our Model Score")
    advanced_chart_score: float | None = Field(default=None, alias="Advanced Chart Score")
    best_marriage_window: str | None = Field(default=None, alias="Best Marriage Window")
    average_score: float = Field(..., alias="Average Score")
    filter_status: str | None = Field(default=None, alias="Filter Status")
    rejection_reason: str | None = Field(default=None, alias="Rejection Reason")
    compatibility_warning: str | None = Field(default=None, alias="Compatibility Warning")
    rank: int = Field(..., alias="Rank")
    notes: dict[str, Any] = Field(default_factory=dict, alias="Notes")

    model_config = {"populate_by_name": True}
