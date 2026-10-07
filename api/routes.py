from __future__ import annotations

import json
import os
import re
import uuid
from datetime import date, datetime, time
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, Response, UploadFile

from backend.compatibility_engine.compatibility_service import CompatibilityService
from backend.filtering_engine.filter_service import FilteringService
from backend.models.schemas import PersonDetails
from backend.prokerala_engine.prokerala_client import ProkeralaClient
from backend.swiss_engine.horoscope_generator import HoroscopeGenerator
from backend.utils.config import get_settings
from backend.utils.excel_io import dataframe_to_records, read_excel_bytes, write_excel
from backend.utils.geocoding import GeocodingService, timezone_offset
from backend.vedastro_engine.vedastro_client import VedAstroClient

router = APIRouter()
_LOCAL_COMPATIBILITY_JOBS: dict[str, dict[str, Any]] = {}


_CANDIDATE_FIELD_ALIASES = {
    "Id": ("Id", "id", "row_id"),
    "Name": ("Name", "name"),
    "Gender": ("Gender", "gender"),
    "Age": ("Age", "age"),
    "DOB": ("DOB", "dob"),
    "TOB": ("TOB", "tob"),
    "POB": ("POB", "pob"),
    "Latitude": ("Latitude", "latitude"),
    "Longitude": ("Longitude", "longitude"),
    "Timezone": ("Timezone", "timezone"),
    "Star": ("Star", "star", "Nakshathra", "nakshathra", "Nakshatra", "nakshatra"),
    "Gotram": ("Gotram", "gotram", "Gothram", "gothram"),
    "Education": ("Education", "education", "Study", "study"),
    "Job": ("Job", "job"),
    "Contact": ("Contact", "contact"),
}


def _parse_person(person_json: str) -> PersonDetails:
    return PersonDetails.model_validate(json.loads(person_json))


def _candidate_dataframe_from_json(candidate_json: str) -> Any:
    import pandas as pd

    raw = json.loads(candidate_json)
    if not isinstance(raw, dict):
        raise ValueError("candidate_json must be a single candidate object")

    record: dict[str, Any] = {}
    for column, aliases in _CANDIDATE_FIELD_ALIASES.items():
        for alias in aliases:
            if alias in raw:
                record[column] = raw[alias]
                break

    record.setdefault("Id", 1)
    record.setdefault("Gender", "Female")
    for column in ("Name", "DOB", "TOB", "POB", "Star", "Gotram", "Education", "Job", "Contact"):
        record.setdefault(column, None)

    required = ("Name", "DOB", "TOB", "POB", "Star", "Gotram", "Education")
    missing = [column for column in required if record.get(column) in (None, "")]
    if missing:
        raise ValueError(f"candidate_json missing required fields: {', '.join(missing)}")

    return pd.DataFrame([record])


async def _candidate_dataframe_from_input(file: UploadFile | None, candidate_json: str | None) -> Any:
    if file is not None and file.filename:
        return read_excel_bytes(await file.read())
    if candidate_json:
        return _candidate_dataframe_from_json(candidate_json)
    raise ValueError("Provide either an Excel file or candidate_json")


def _parse_candidate_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    parsed = datetime.strptime(str(value).strip(), "%Y-%m-%d") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value).strip()) else None
    if parsed:
        return parsed.date()

    import pandas as pd

    dob = pd.to_datetime(value, errors="coerce", dayfirst=True)
    if pd.isna(dob):
        raise ValueError(f"Invalid candidate DOB: {value}")
    return dob.date()


def _parse_candidate_time(value: Any) -> time:
    if isinstance(value, datetime):
        return value.time().replace(microsecond=0)
    if isinstance(value, time):
        return value.replace(microsecond=0)

    cleaned = _clean_candidate_time(str(value))
    for time_format in ("%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p", "%I %p"):
        try:
            return datetime.strptime(cleaned.upper(), time_format).time()
        except ValueError:
            continue

    separated_match = re.fullmatch(r"(\d{1,2})\s*([\.\-;,/])\s*(\d{1,2})\s*(AM|PM)?", cleaned.upper())
    if separated_match:
        minute_text = separated_match.group(3)
        minute = int(minute_text) if len(minute_text) == 2 else int(minute_text) * 10
        parsed = _time_from_parts(int(separated_match.group(1)), minute, separated_match.group(4))
        if parsed:
            return parsed

    compact_match = re.fullmatch(r"(\d{1,2})(\d{2})\s*(AM|PM)?", cleaned.upper())
    if compact_match:
        parsed = _time_from_parts(int(compact_match.group(1)), int(compact_match.group(2)), compact_match.group(3))
        if parsed:
            return parsed

    hour_match = re.fullmatch(r"(\d{1,2})\s*(AM|PM)?", cleaned.upper())
    if hour_match:
        parsed = _time_from_parts(int(hour_match.group(1)), 0, hour_match.group(2))
        if parsed:
            return parsed

    raise ValueError(f"Invalid candidate TOB: {value}")


def _time_from_parts(hour: int, minute: int, suffix: str | None = None) -> time | None:
    if not 0 <= minute <= 59:
        return None
    if suffix:
        if not 1 <= hour <= 12:
            return None
        if suffix == "PM" and hour != 12:
            hour += 12
        elif suffix == "AM" and hour == 12:
            hour = 0
    elif not 0 <= hour <= 23:
        return None
    return time(hour, minute)


def _clean_candidate_time(value: str) -> str:
    cleaned = value.strip().upper().replace("O", "0")
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s*:\s*", ":", cleaned)
    cleaned = re.sub(r"(\d)(AM|PM)$", r"\1 \2", cleaned)
    return cleaned


def _needs_location(record: dict[str, Any]) -> bool:
    return record.get("Latitude") is None or record.get("Longitude") is None or record.get("Timezone") is None


def _ensure_id_column(df: Any) -> Any:
    if df.empty:
        return df
    result = df.copy()
    if "Id" not in result.columns:
        result.insert(0, "Id", range(1, len(result) + 1))
    else:
        result["Id"] = result["Id"].where(result["Id"].notna(), range(1, len(result) + 1))
    return result


async def _candidate_person(record: dict[str, Any], geocoding: GeocodingService) -> PersonDetails:
    record["DOB"] = _parse_candidate_date(record.get("DOB")).isoformat()
    tob = _parse_candidate_time(record.get("TOB"))
    record["TOB"] = tob.isoformat()

    if _needs_location(record):
        places = await geocoding.search_places(str(record.get("POB") or ""), limit=1)
        if not places:
            raise ValueError(f"Could not calculate candidate location from POB: {record.get('POB')}")
        place = places[0]
        record["Latitude"] = record.get("Latitude") if record.get("Latitude") is not None else place["latitude"]
        record["Longitude"] = record.get("Longitude") if record.get("Longitude") is not None else place["longitude"]
        timezone_name = place.get("timezone")
        if record.get("Timezone") is None and not timezone_name:
            timezone_name = await geocoding.timezone_name(float(record["Latitude"]), float(record["Longitude"]))
        if record.get("Timezone") is None and timezone_name:
            record["Timezone"] = timezone_offset(timezone_name, _parse_candidate_date(record["DOB"]), tob)
        if record.get("Timezone") is None:
            raise ValueError(f"Could not calculate candidate timezone from POB: {record.get('POB')}")

    return PersonDetails.model_validate(record)


async def _candidate_people(records: list[dict[str, Any]], geocoding: GeocodingService) -> tuple[list[PersonDetails], list[dict[str, str]]]:
    import asyncio

    async def _safe(record: dict[str, Any]) -> PersonDetails | dict[str, str]:
        try:
            return await _candidate_person(record, geocoding)
        except Exception as exc:
            return {
                "Id": str(record.get("Id") or ""),
                "Name": str(record.get("Name") or ""),
                "POB": str(record.get("POB") or ""),
                "Reason": str(exc),
            }

    results = await asyncio.gather(*(_safe(r) for r in records))
    candidates = [r for r in results if isinstance(r, PersonDetails)]
    errors = [r for r in results if isinstance(r, dict)]
    return candidates, errors


@router.get("/places/search")
async def search_places(q: str = Query(..., min_length=2), limit: int = Query(8, ge=1, le=10)) -> dict:
    try:
        places = await GeocodingService().search_places(q, limit)
        return {"places": places}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Place search failed: {exc}") from exc


@router.post("/filter-users")
async def filter_users(
    person_json: str = Form(...),
    file: UploadFile | None = File(None),
    candidate_json: str | None = Form(None),
) -> dict:
    try:
        settings = get_settings()
        person = _parse_person(person_json)
        df = await _candidate_dataframe_from_input(file, candidate_json)
        service = FilteringService(settings.outputs_dir)
        filtered, rejected = service.filter_users_with_rejections(person, df)
        path = service.export_filtered_users(filtered)
        rejected_path = service.export_rejected_users(rejected)
        return {
            "count": len(filtered),
            "rejected_count": len(rejected),
            "output_file": str(path),
            "rejected_file": str(rejected_path),
            "users": dataframe_to_records(filtered),
            "rejected_users": dataframe_to_records(rejected),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/generate-compatibility")
async def generate_compatibility(
    background_tasks: BackgroundTasks,
    response: Response,
    person_json: str = Form(...),
    file: UploadFile | None = File(None),
    candidate_json: str | None = Form(None),
) -> dict:
    try:
        if _should_queue_compatibility_job(file):
            response.status_code = 202
            return await _queue_compatibility_job(person_json, file, candidate_json)
        if _should_queue_local_compatibility_job(file):
            response.status_code = 202
            return await _queue_local_compatibility_job(background_tasks, person_json, file, candidate_json)
        person = _parse_person(person_json)
        df = await _candidate_dataframe_from_input(file, candidate_json)
        return await _generate_compatibility_response(person, df)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/compatibility-jobs/{job_id}")
async def compatibility_job_status(job_id: str) -> dict:
    try:
        status = _get_job_status(job_id) if _is_aws_lambda() else _get_local_job_status(job_id)
        if not status:
            raise HTTPException(status_code=404, detail="Compatibility job not found")
        if status.get("status") == "done" and _is_aws_lambda():
            result = _get_job_result(status)
            if result is not None:
                status["result"] = result
        return status
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/job-status/{job_id}")
async def job_status(job_id: str) -> dict:
    return await compatibility_job_status(job_id)


@router.post("/export-results")
async def export_results(records_json: str = Form(...)) -> dict:
    try:
        import pandas as pd

        settings = get_settings()
        records = json.loads(records_json)
        path = write_excel(pd.DataFrame(records), settings.outputs_dir / "compatibility_results.xlsx")
        return {"output_file": str(path)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _is_aws_lambda() -> bool:
    return bool(os.getenv("AWS_LAMBDA_FUNCTION_NAME"))


def _should_queue_compatibility_job(file: UploadFile | None) -> bool:
    return _is_aws_lambda() and bool(os.getenv("ASTRO_WORKER_FUNCTION_NAME"))


def _should_queue_local_compatibility_job(file: UploadFile | None) -> bool:
    if _is_aws_lambda():
        return False
    queue_setting = os.getenv("ASTRO_QUEUE_COMPATIBILITY", "").strip().lower()
    if queue_setting in {"1", "true", "yes", "on"}:
        return True
    return _has_file(file)


def _has_file(file: UploadFile | None) -> bool:
    return file is not None and bool(file.filename)


async def _queue_compatibility_job(
    person_json: str,
    file: UploadFile | None,
    candidate_json: str | None,
) -> dict:
    import boto3

    bucket = os.getenv("S3_BUCKET")
    worker_name = os.getenv("ASTRO_WORKER_FUNCTION_NAME")
    if not bucket or not worker_name:
        raise RuntimeError("Async compatibility worker is not configured")

    job_id = uuid.uuid4().hex
    payload: dict[str, Any] = {"job_id": job_id, "person_json": person_json}
    status: dict[str, Any] = {"status": "queued", "job_id": job_id}
    if file is not None and file.filename:
        input_key = f"astro_inputs/{job_id}.xlsx"
        file_bytes = await file.read()
        if not file_bytes:
            raise ValueError("Uploaded file is empty")
        boto3.client("s3").put_object(
            Bucket=bucket,
            Key=input_key,
            Body=file_bytes,
            ContentType=file.content_type or "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        payload["input_key"] = input_key
        status["input_key"] = input_key
    elif candidate_json:
        payload["candidate_json"] = candidate_json
    else:
        raise ValueError("Provide either an Excel file or candidate_json")

    _put_job_status(job_id, status)
    boto3.client("lambda").invoke(
        FunctionName=worker_name,
        InvocationType="Event",
        Payload=json.dumps(payload).encode("utf-8"),
    )
    return {
        "status": "queued",
        "job_id": job_id,
        "status_url": f"/job-status/{job_id}",
        "message": "Compatibility scoring is running in the background. Poll status_url for the result.",
    }


async def _queue_local_compatibility_job(
    background_tasks: BackgroundTasks,
    person_json: str,
    file: UploadFile | None,
    candidate_json: str | None,
) -> dict:
    job_id = uuid.uuid4().hex
    file_bytes: bytes | None = None
    filename: str | None = None
    if _has_file(file):
        file_bytes = await file.read()
        filename = file.filename
        if not file_bytes:
            raise ValueError("Uploaded file is empty")
    elif not candidate_json:
        raise ValueError("Provide either an Excel file or candidate_json")

    _put_local_job_status(job_id, {"status": "queued", "job_id": job_id, "filename": filename})
    background_tasks.add_task(_run_local_compatibility_job, job_id, person_json, file_bytes, candidate_json)
    return {
        "status": "queued",
        "job_id": job_id,
        "status_url": f"/job-status/{job_id}",
        "message": "Compatibility scoring is running in the background. Poll status_url for the result.",
    }


async def _run_local_compatibility_job(
    job_id: str,
    person_json: str,
    file_bytes: bytes | None,
    candidate_json: str | None,
) -> None:
    try:
        _put_local_job_status(job_id, {"status": "running", "job_id": job_id})
        person = _parse_person(person_json)
        if file_bytes is not None:
            df = read_excel_bytes(file_bytes)
        elif candidate_json:
            df = _candidate_dataframe_from_json(candidate_json)
        else:
            raise ValueError("Worker event must include file bytes or candidate_json")
        result = await _generate_compatibility_response(person, df)
        _put_local_job_status(job_id, {"status": "done", "job_id": job_id, "result": result})
    except Exception as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        _put_local_job_status(job_id, {"status": "error", "job_id": job_id, "error": detail})


def _put_local_job_status(job_id: str, data: dict[str, Any]) -> None:
    _LOCAL_COMPATIBILITY_JOBS[job_id] = data


def _get_local_job_status(job_id: str) -> dict[str, Any] | None:
    status = _LOCAL_COMPATIBILITY_JOBS.get(job_id)
    return dict(status) if status else None


def _put_job_status(job_id: str, data: dict[str, Any]) -> None:
    import boto3

    table_name = os.getenv("DYNAMO_TABLE")
    if not table_name:
        return
    boto3.resource("dynamodb").Table(table_name).put_item(
        Item={"pk": f"astro_job#{job_id}", "data": data}
    )


def _get_job_status(job_id: str) -> dict[str, Any] | None:
    import boto3

    table_name = os.getenv("DYNAMO_TABLE")
    if not table_name:
        raise RuntimeError("DYNAMO_TABLE is not configured")
    response = boto3.resource("dynamodb").Table(table_name).get_item(
        Key={"pk": f"astro_job#{job_id}"}
    )
    item = response.get("Item")
    return item.get("data") if item else None


def _get_job_result(status: dict[str, Any]) -> dict[str, Any] | None:
    bucket = os.getenv("S3_BUCKET")
    json_key = status.get("json_key")
    if not bucket or not json_key:
        return None
    import boto3

    response = boto3.client("s3").get_object(Bucket=bucket, Key=json_key)
    return json.loads(response["Body"].read().decode("utf-8"))


async def _generate_compatibility_response(person: PersonDetails, df: Any) -> dict:
    settings = get_settings()
    filtering = FilteringService(settings.outputs_dir)
    df = _ensure_id_column(df)
    filtered, rejected = filtering.filter_users_with_rejections(person, df)
    filtered = _ensure_id_column(filtered)
    rejected = _ensure_id_column(rejected)
    filtering.export_filtered_users(filtered)
    rejected_path = filtering.export_rejected_users(rejected)
    geocoding = GeocodingService()
    filtered_records = dataframe_to_records(filtered)
    rejected_records = dataframe_to_records(rejected)
    all_records = filtered_records + rejected_records
    candidates, candidate_errors = await _candidate_people(all_records, geocoding)
    rejected_reasons = {
        str(record.get("Id")): str(record.get("Rejection Reason") or "")
        for record in rejected_records
        if record.get("Id") is not None
    }
    compatibility_warnings = {
        str(record.get("Id")): str(record.get("Compatibility Warning") or "")
        for record in all_records
        if record.get("Id") is not None and record.get("Compatibility Warning")
    }
    import asyncio as _asyncio
    service = CompatibilityService(ProkeralaClient(settings), VedAstroClient(settings))
    try:
        results = await _asyncio.wait_for(service.generate(person, candidates), timeout=_compatibility_timeout_seconds())
    except _asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Compatibility scoring timed out. Try with fewer candidates.")
    results = _annotate_filter_status(results, rejected_reasons, compatibility_warnings)
    passed_results, rejected_results = _split_results_by_filter_status(results)
    horoscope_generator = HoroscopeGenerator()
    source_horoscope = horoscope_generator.generate(person)
    candidate_horoscopes = {
        str(candidate.row_id): horoscope_generator.generate(candidate)
        for candidate in candidates
        if candidate.row_id is not None
    }
    export_df = results.drop(columns=["Notes"], errors="ignore")
    path = write_excel(export_df, settings.outputs_dir / "compatibility_results.xlsx")
    return {
        "filtered_count": len(filtered),
        "rejected_count": len(rejected),
        "result_count": len(passed_results),
        "rejected_result_count": len(rejected_results),
        "all_result_count": len(results),
        "filtered_file": str(settings.outputs_dir / "filtered_users.xlsx"),
        "rejected_file": str(rejected_path),
        "results_file": str(path),
        "filtered_users": dataframe_to_records(filtered),
        "rejected_users": dataframe_to_records(rejected),
        "results": dataframe_to_records(passed_results.drop(columns=["Notes"], errors="ignore")),
        "rejected_results": dataframe_to_records(rejected_results.drop(columns=["Notes"], errors="ignore")),
        "all_results": dataframe_to_records(results.drop(columns=["Notes"], errors="ignore")),
        "explanations": dataframe_to_records(passed_results[["Name", "Notes"]]) if not passed_results.empty else [],
        "rejected_explanations": dataframe_to_records(rejected_results[["Name", "Notes"]]) if not rejected_results.empty else [],
        "all_explanations": dataframe_to_records(results[["Name", "Notes"]]) if not results.empty else [],
        "source_horoscope": source_horoscope,
        "candidate_errors": candidate_errors,
        "candidate_horoscopes": candidate_horoscopes,
    }


def _compatibility_timeout_seconds() -> float:
    try:
        return float(os.getenv("COMPATIBILITY_SCORE_TIMEOUT_SECONDS", "60"))
    except ValueError:
        return 60.0


def _annotate_filter_status(
    results: Any,
    rejected_reasons: dict[str, str],
    compatibility_warnings: dict[str, str],
) -> Any:
    if results.empty:
        return results
    annotated = results.copy()
    rejected_ids = set(rejected_reasons)
    annotated["Filter Status"] = annotated["Id"].map(
        lambda value: "Rejected" if str(value) in rejected_ids else "Passed"
    )
    annotated["Rejection Reason"] = annotated["Id"].map(
        lambda value: rejected_reasons.get(str(value))
    )
    annotated["Compatibility Warning"] = annotated["Id"].map(
        lambda value: compatibility_warnings.get(str(value))
    )

    column_order = [
        column
        for column in annotated.columns
        if column not in {"Filter Status", "Rejection Reason", "Compatibility Warning", "Notes"}
    ]
    column_order.extend(["Filter Status", "Rejection Reason", "Compatibility Warning", "Notes"])
    return annotated[column_order]


def _split_results_by_filter_status(results: Any) -> tuple[Any, Any]:
    if results.empty or "Filter Status" not in results.columns:
        return results, results.iloc[0:0].copy()
    passed = results[results["Filter Status"] != "Rejected"].reset_index(drop=True)
    rejected = results[results["Filter Status"] == "Rejected"].reset_index(drop=True)
    return passed, rejected
