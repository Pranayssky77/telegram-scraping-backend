from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd


def read_excel_bytes(data: bytes) -> pd.DataFrame:
    return pd.read_excel(BytesIO(data), engine="openpyxl")


def write_excel(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return path


def dataframe_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    clean = df.replace({pd.NA: None}).where(pd.notnull(df), None)
    return [
        {key: _json_safe(value, key) for key, value in row.items()}
        for row in clean.to_dict(orient="records")
    ]


def _json_safe(value: Any, key: str | None = None) -> Any:
    if value is None or pd.isna(value):
        return None
    if key == "DOB" and hasattr(value, "date"):
        return value.date().isoformat()
    if key == "TOB" and hasattr(value, "time"):
        return value.time().replace(microsecond=0).isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
