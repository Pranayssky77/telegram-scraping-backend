from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from telethon.errors import SessionPasswordNeededError
from telethon.sync import TelegramClient

from backend.api.routes import router
from backend.utils.config import ROOT_DIR, get_settings
from backend.utils.logging_config import configure_logging

configure_logging()
settings = get_settings()
SCRAPER_OUTPUT_DIR = ROOT_DIR / "output"
SCRAPER_FILE = ROOT_DIR / "telegram" / "telegram_scraper.py"
TELEGRAM_SESSION_BASE = ROOT_DIR / "telegram" / "telegram_session"
TELEGRAM_SESSION_FILE = ROOT_DIR / "telegram" / "telegram_session.session"
TARGETS_FILE = ROOT_DIR / "dashboard" / "targets.json"
CREDS_FILE = ROOT_DIR / "dashboard" / "credentials.local.json"
run_status: dict[str, str | bool | None] = {"running": False, "last_run": None, "last_status": None}
auth_state: dict[str, Any] = {"phone_code_hash": None, "phone": None, "api_id": None, "api_hash": None}
log_events: list[dict[str, str | int]] = []
log_lock = threading.Lock()

app = FastAPI(title=settings.app_name, version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(router, prefix="/astro")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/health")
async def api_health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/astro/health")
async def astro_health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/save_credentials")
async def save_credentials(request: Request) -> dict[str, str]:
    data = await _request_json(request)
    credentials = {
        "api_id": str(data.get("api_id") or "").strip(),
        "api_hash": str(data.get("api_hash") or "").strip(),
        "phone": str(data.get("phone") or "").strip(),
    }
    _save_credentials(credentials)
    return {"status": "success"}


@app.get("/api/get_credentials")
async def get_credentials() -> dict[str, str | bool]:
    credentials = _load_credentials()
    return {
        "api_id": credentials.get("api_id", ""),
        "api_hash": credentials.get("api_hash", ""),
        "phone": credentials.get("phone", ""),
        "is_authorised": _is_dashboard_authorised(credentials),
    }


@app.post("/api/clear_credentials")
async def clear_credentials() -> dict[str, str]:
    try:
        CREDS_FILE.unlink(missing_ok=True)
        TELEGRAM_SESSION_FILE.unlink(missing_ok=True)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    auth_state.update({"phone_code_hash": None, "phone": None, "api_id": None, "api_hash": None})
    return {"status": "success"}


@app.post("/api/request_code")
async def request_code(request: Request) -> dict[str, str]:
    data = await _request_json(request)
    stored = _load_credentials()
    api_id = str(data.get("api_id") or stored.get("api_id") or "").strip()
    api_hash = str(data.get("api_hash") or stored.get("api_hash") or "").strip()
    phone = str(data.get("phone") or stored.get("phone") or "").strip()
    if not all([api_id, api_hash, phone]):
        raise HTTPException(status_code=400, detail="api_id, api_hash and phone are required")
    _save_credentials({"api_id": api_id, "api_hash": api_hash, "phone": phone})
    try:
        return await _send_code(int(api_id), api_hash, phone)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/verify_code")
async def verify_code(request: Request) -> dict[str, str]:
    data = await _request_json(request)
    code = str(data.get("code") or "").strip()
    password = str(data.get("password") or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="OTP code is required")
    if not auth_state.get("phone_code_hash"):
        raise HTTPException(status_code=400, detail="No pending login — call /api/request_code first")
    result = await _verify_code(
        int(auth_state["api_id"]),
        str(auth_state["api_hash"]),
        str(auth_state["phone"]),
        code,
        str(auth_state["phone_code_hash"]),
        password,
    )
    if result.get("status") == "ok":
        auth_state["phone_code_hash"] = None
    return result


@app.get("/api/targets")
async def get_targets() -> dict[str, list[str]]:
    return {"targets": _load_targets()}


@app.post("/api/targets")
async def save_targets(request: Request) -> dict[str, str | list[str]]:
    data = await request.json()
    targets = _clean_targets(data.get("targets", []))
    _save_targets(targets)
    return {"status": "success", "targets": targets}


@app.post("/api/targets/add")
async def add_target(request: Request) -> dict[str, str | list[str]]:
    data = await request.json()
    name = str(data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Target name is required")
    targets = _load_targets()
    if name in targets:
        raise HTTPException(status_code=409, detail="Target already in list")
    targets.append(name)
    _save_targets(targets)
    return {"status": "success", "targets": targets}


@app.post("/api/targets/remove")
async def remove_target(request: Request) -> dict[str, str | list[str]]:
    data = await request.json()
    name = str(data.get("name") or "").strip()
    targets = [target for target in _load_targets() if target != name]
    _save_targets(targets)
    return {"status": "success", "targets": targets}


@app.get("/api/status")
async def dashboard_status() -> dict[str, str | bool | None]:
    return {**run_status, "is_authorised": _is_dashboard_authorised()}


@app.post("/api/run")
async def run_scraper(request: Request) -> dict[str, str]:
    if run_status["running"]:
        raise HTTPException(status_code=409, detail="Scraper is already running!")
    if not SCRAPER_FILE.exists():
        raise HTTPException(status_code=404, detail=f"Scraper not found at: {SCRAPER_FILE}")
    if not TELEGRAM_SESSION_FILE.exists():
        raise HTTPException(status_code=400, detail="Not authorised — please login first via the Auth panel.")

    credentials = _load_credentials()
    api_id = credentials.get("api_id")
    api_hash = credentials.get("api_hash")
    phone = credentials.get("phone")
    if not all([api_id, api_hash, phone]):
        raise HTTPException(status_code=400, detail="Telegram credentials missing — set them in the Auth panel.")

    targets = _load_targets()
    if not targets:
        raise HTTPException(status_code=400, detail="No target groups set — add at least one group in the Auth panel.")

    data = await _request_json(request)
    extra_code = str(data.get("code") or "")
    _start_scraper_thread(str(api_id), str(api_hash), str(phone), targets, extra_code)
    return {"status": "success", "message": "Scraper started!"}


@app.get("/api/logs")
async def get_logs(request: Request) -> dict[str, list[dict[str, str | int]] | str]:
    try:
        next_token = int(request.query_params.get("nextToken") or 0)
    except ValueError:
        next_token = 0
    with log_lock:
        events = log_events[next_token:]
        new_token = len(log_events)
    return {"events": events, "nextToken": str(new_token)}


@app.get("/api/files")
async def dashboard_files() -> list[dict[str, str | int]]:
    files: list[dict[str, str | int]] = []
    SCRAPER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in [*SCRAPER_OUTPUT_DIR.glob("*.xlsx"), *SCRAPER_OUTPUT_DIR.glob("*.json")]:
        stat = path.stat()
        files.append(
            {
                "name": path.name,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "type": "excel" if path.suffix == ".xlsx" else "json",
            }
        )
    return sorted(files, key=lambda file: str(file["modified"]), reverse=True)


@app.get("/api/download/{filename}")
async def dashboard_download(filename: str, request: Request) -> dict[str, str]:
    _output_file(filename)
    url = str(request.url_for("dashboard_file_content", filename=filename))
    return {"url": url}


@app.get("/api/files/{filename}/content", name="dashboard_file_content")
async def dashboard_file_content(filename: str) -> FileResponse:
    path = _output_file(filename)
    return FileResponse(path, filename=filename)


@app.delete("/api/files/{filename}")
async def delete_file(filename: str) -> dict[str, str]:
    path = _output_file(filename)
    try:
        path.unlink()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"deleted": filename}


@app.get("/api/dialogs")
async def list_dialogs() -> dict[str, list[dict[str, str | int | None]]]:
    credentials = _load_credentials()
    if not all([credentials.get("api_id"), credentials.get("api_hash")]):
        raise HTTPException(status_code=400, detail="Telegram credentials missing — set them in the Auth panel.")
    if not TELEGRAM_SESSION_FILE.exists():
        return {"dialogs": []}
    try:
        dialogs = await _list_dialogs(int(credentials["api_id"]), str(credentials["api_hash"]))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"dialogs": dialogs}


async def _send_code(api_id: int, api_hash: str, phone: str) -> dict[str, str]:
    client = TelegramClient(str(TELEGRAM_SESSION_BASE), api_id, api_hash)
    await client.connect()
    try:
        if await client.is_user_authorized():
            return {"status": "already_authorised", "message": "Session already active — no code needed."}
        sent = await client.send_code_request(phone)
        auth_state.update(
            {
                "phone_code_hash": sent.phone_code_hash,
                "phone": phone,
                "api_id": api_id,
                "api_hash": api_hash,
            }
        )
        return {"status": "code_sent", "message": f"OTP sent to {phone}. Enter it below."}
    finally:
        await client.disconnect()


async def _verify_code(
    api_id: int,
    api_hash: str,
    phone: str,
    code: str,
    phone_code_hash: str,
    password: str,
) -> dict[str, str]:
    client = TelegramClient(str(TELEGRAM_SESSION_BASE), api_id, api_hash)
    await client.connect()
    try:
        try:
            await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        except SessionPasswordNeededError:
            if not password:
                return {"status": "need_2fa", "message": "2-FA password required. Please provide it."}
            await client.sign_in(password=password)
        except Exception as exc:
            return {"status": "error", "message": str(exc)}
        me = await client.get_me()
        return {"status": "ok", "message": f"Logged in as {me.username or me.first_name}"}
    finally:
        await client.disconnect()


async def _list_dialogs(api_id: int, api_hash: str) -> list[dict[str, str | int | None]]:
    client = TelegramClient(str(TELEGRAM_SESSION_BASE), api_id, api_hash)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            return []
        dialogs: list[dict[str, str | int | None]] = []
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            dialogs.append(
                {
                    "id": int(dialog.id),
                    "name": dialog.name or "",
                    "username": getattr(entity, "username", None),
                    "type": "channel" if getattr(entity, "broadcast", False) else ("group" if getattr(entity, "megagroup", False) or getattr(entity, "gigagroup", False) else "chat"),
                }
            )
        return dialogs
    finally:
        await client.disconnect()


def _start_scraper_thread(api_id: str, api_hash: str, phone: str, targets: list[str], extra_code: str) -> None:
    def run() -> None:
        run_status["running"] = True
        run_status["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        run_status["last_status"] = None
        _clear_logs()
        _append_log(f"[{run_status['last_run']}] [INFO] Starting Telegram scraper...\n")
        try:
            env = os.environ.copy()
            env["PYTHONUTF8"] = "1"
            env["TELEGRAM_API_ID"] = api_id
            env["TELEGRAM_API_HASH"] = api_hash
            env["TELEGRAM_PHONE"] = phone
            env["TELEGRAM_CODE"] = extra_code
            env["TELEGRAM_TARGETS"] = "\n".join(targets)
            proc = subprocess.Popen(
                [sys.executable, "-X", "utf8", str(SCRAPER_FILE)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=str(SCRAPER_FILE.parent),
                env=env,
            )
            if proc.stdout:
                for line in proc.stdout:
                    _append_log(line)
            proc.wait()
            run_status["last_status"] = "success" if proc.returncode == 0 else "error"
            _append_log(f"\n[INFO] Scraper finished (exit code {proc.returncode})\n")
        except Exception as exc:
            run_status["last_status"] = "error"
            _append_log(f"\n[ERROR] {exc}\n")
        finally:
            run_status["running"] = False

    threading.Thread(target=run, daemon=True).start()


def _append_log(message: str) -> None:
    with log_lock:
        log_events.append({"id": len(log_events), "message": message})


def _clear_logs() -> None:
    with log_lock:
        log_events.clear()


async def _request_json(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _load_credentials() -> dict[str, str]:
    data: dict[str, Any] = {}
    if CREDS_FILE.exists():
        try:
            loaded = json.loads(CREDS_FILE.read_text())
            data = loaded if isinstance(loaded, dict) else {}
        except (OSError, json.JSONDecodeError):
            data = {}
    return {
        "api_id": str(data.get("api_id") or os.getenv("TELEGRAM_API_ID") or "").strip(),
        "api_hash": str(data.get("api_hash") or os.getenv("TELEGRAM_API_HASH") or "").strip(),
        "phone": str(data.get("phone") or os.getenv("TELEGRAM_PHONE") or "").strip(),
    }


def _save_credentials(credentials: dict[str, str]) -> None:
    CREDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CREDS_FILE.write_text(json.dumps(credentials, indent=2))


def _is_dashboard_authorised(credentials: dict[str, str] | None = None) -> bool:
    credentials = credentials or _load_credentials()
    return TELEGRAM_SESSION_FILE.exists() and all(
        [credentials.get("api_id"), credentials.get("api_hash"), credentials.get("phone")]
    )


def _output_file(filename: str) -> Path:
    path = SCRAPER_OUTPUT_DIR / filename
    if path.name != filename or not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")
    return path


def _load_targets() -> list[str]:
    if not TARGETS_FILE.exists():
        return []
    try:
        data: Any = json.loads(TARGETS_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, dict):
        return _clean_targets(data.get("targets", []))
    if isinstance(data, list):
        return _clean_targets(data)
    return []


def _save_targets(targets: list[str]) -> None:
    TARGETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TARGETS_FILE.write_text(json.dumps({"targets": targets}, indent=2))


def _clean_targets(raw_targets: Any) -> list[str]:
    if not isinstance(raw_targets, list):
        return []
    targets: list[str] = []
    for target in raw_targets:
        cleaned = str(target).strip()
        if cleaned and cleaned not in targets:
            targets.append(cleaned)
    return targets
