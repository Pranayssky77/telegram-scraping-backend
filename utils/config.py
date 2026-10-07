from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    app_name: str
    prokerala_client_id: str | None
    prokerala_client_secret: str | None
    prokerala_token_url: str
    prokerala_match_url: str
    prokerala_request_delay_seconds: float
    prokerala_max_retries: int
    prokerala_retry_base_seconds: float
    vedastro_api_key: str
    outputs_dir: Path
    uploads_dir: Path


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


@lru_cache
def get_settings() -> Settings:
    settings = Settings(
        app_name="Astrology Matrimony Matching System",
        prokerala_client_id=os.getenv("PROKERALA_CLIENT_ID"),
        prokerala_client_secret=os.getenv("PROKERALA_CLIENT_SECRET"),
        prokerala_token_url=os.getenv("PROKERALA_TOKEN_URL", "https://api.prokerala.com/token"),
        prokerala_match_url=os.getenv(
            "PROKERALA_MATCH_URL",
            "https://api.prokerala.com/v2/astrology/kundli-matching",
        ),
        prokerala_request_delay_seconds=_float_env("PROKERALA_REQUEST_DELAY_SECONDS", 2.0),
        prokerala_max_retries=_int_env("PROKERALA_MAX_RETRIES", 6),
        prokerala_retry_base_seconds=_float_env("PROKERALA_RETRY_BASE_SECONDS", 5.0),
        vedastro_api_key=os.getenv("VEDASTRO_API_KEY", "FreeAPIUser"),
        outputs_dir=Path(os.getenv("OUTPUTS_DIR", "/tmp/outputs" if os.getenv("AWS_LAMBDA_FUNCTION_NAME") else ROOT_DIR / "outputs")),
        uploads_dir=Path(os.getenv("UPLOADS_DIR", "/tmp/uploads" if os.getenv("AWS_LAMBDA_FUNCTION_NAME") else ROOT_DIR / "uploads")),
    )
    settings.outputs_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    return settings
