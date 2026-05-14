import importlib.util
import hashlib
import json
import os
import socket
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

from src.core.config import (
    ALOSConfig,
    DATA_DIR,
    ENV_PATH,
    ROOT_DIR,
    PROVIDER_DEFAULT_BASE_URL,
    SUPPORTED_PROVIDERS,
    config,
)


REQUIRED_MODULES = [
    "fastapi",
    "uvicorn",
    "langchain_core",
    "langchain_openai",
    "langgraph",
    "pydantic",
    "chromadb",
    "sentence_transformers",
]

SETUP_STATE_PATH = os.environ.get("ALOS_SETUP_STATE_PATH", str(DATA_DIR / "setup_status.json"))


@dataclass(frozen=True)
class SetupCheck:
    name: str
    ok: bool
    detail: str


def port_status(port: int = 8000) -> SetupCheck:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.2)
    try:
        result = sock.connect_ex(("127.0.0.1", port))
        if result == 0:
            return SetupCheck("port_8000", False, f"Port {port} is already in use.")
        return SetupCheck("port_8000", True, f"Port {port} is available.")
    finally:
        sock.close()


def api_key_fingerprint(api_key: str) -> str:
    value = (api_key or "").strip()
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def available_port_diagnostics(start: int = 8000, count: int = 8) -> dict[str, Any]:
    ports = []
    recommended = None
    for port in range(start, start + count):
        check = port_status(port)
        ports.append({"port": port, "available": check.ok, "detail": check.detail})
        if recommended is None and check.ok:
            recommended = port
    return {
        "recommended_port": recommended,
        "ports": ports,
        "mode": "automatic",
        "advanced_override_supported": True,
    }


def dependency_status() -> list[SetupCheck]:
    checks = []
    for module in REQUIRED_MODULES:
        checks.append(
            SetupCheck(
                name=f"module:{module}",
                ok=importlib.util.find_spec(module) is not None,
                detail=f"{module} import {'available' if importlib.util.find_spec(module) is not None else 'missing'}",
            )
        )
    return checks


def _read_setup_state() -> dict[str, Any]:
    path = Path(SETUP_STATE_PATH)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_setup_state(payload: dict[str, Any]) -> dict[str, Any]:
    path = Path(SETUP_STATE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _public_validation(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if key != "api_key_fingerprint"}


def _stored_validation() -> dict[str, Any]:
    return _read_setup_state().get("last_validation", {})


def last_validation() -> dict[str, Any]:
    return _public_validation(_stored_validation())


def store_validation_result(result: dict[str, Any]) -> dict[str, Any]:
    state = _read_setup_state()
    state["last_validation"] = {
        **result,
        "validated_at": datetime.utcnow().isoformat(),
        "provider": result.get("provider"),
        "model": result.get("model"),
        "base_url": result.get("base_url"),
        "api_key_fingerprint": result.get("api_key_fingerprint"),
    }
    return _public_validation(_write_setup_state(state)["last_validation"])


def store_setup_status(status: dict[str, Any]) -> dict[str, Any]:
    state = _read_setup_state()
    state["last_status"] = {
        "ready": status.get("ready", False),
        "state": status.get("state"),
        "next_action": status.get("next_action"),
        "checked_at": datetime.utcnow().isoformat(),
    }
    _write_setup_state(state)
    return state["last_status"]


def setup_status() -> dict[str, Any]:
    dependencies = dependency_status()
    dependency_ok = all(check.ok for check in dependencies)
    config_ok = config.is_configured()
    validation = _stored_validation()
    validation_matches_current = (
        validation.get("provider") == config.llm_provider
        and validation.get("model") == config.model_name
        and (validation.get("base_url") or "") == (config.base_url or "")
        and validation.get("api_key_fingerprint") == api_key_fingerprint(config.api_key)
    )

    if not config_ok:
        state = "missing_config"
        next_action = "Enter provider, model, base URL, and API key."
    elif not dependency_ok:
        state = "repair_needed"
        next_action = "Repair missing Python dependencies."
    elif not validation_matches_current or validation.get("ok") is not True:
        state = "provider_invalid"
        next_action = "Validate provider settings before running ALOS."
    else:
        state = "ready"
        next_action = "ALOS is ready."

    checks = [
        SetupCheck("workspace", ROOT_DIR.exists(), str(ROOT_DIR)),
        SetupCheck("env_file", ENV_PATH.exists(), str(ENV_PATH)),
        SetupCheck("provider_config", config.is_configured(), "Provider key/model configured." if config.is_configured() else "Provider setup is incomplete."),
        *dependencies,
    ]
    status = {
        "ready": state == "ready",
        "state": state,
        "checks": [check.__dict__ for check in checks],
        "ports": available_port_diagnostics(),
        "last_validation": _public_validation(validation),
        "next_action": next_action,
    }
    status["last_status"] = store_setup_status(status)
    return status


def validate_provider_payload(payload: dict) -> dict[str, Any]:
    provider = str(payload.get("llm_provider") or "").strip().lower()
    model = str(payload.get("model_name") or "").strip()
    api_key = str(payload.get("api_key") or config.api_key or "").strip()
    base_url = str(payload.get("base_url") or config.base_url or "").strip()

    # Fall back to provider default base_url when user leaves it blank.
    if not base_url and provider in PROVIDER_DEFAULT_BASE_URL:
        default = PROVIDER_DEFAULT_BASE_URL[provider]
        if default:
            base_url = default

    errors = []
    if not provider:
        errors.append("Provider is required.")
    elif provider not in SUPPORTED_PROVIDERS:
        errors.append(f"Unknown provider '{provider}'.")
    if not model:
        errors.append("Model is required.")
    # Ollama is local and unauthenticated. Every other provider needs a real key.
    if provider != "ollama" and len(api_key) < 10:
        errors.append("API key is missing or too short.")
    # openai_compatible has no default base_url — user must supply one.
    if provider == "openai_compatible" and not base_url:
        errors.append("Base URL is required for custom OpenAI-compatible providers.")
    candidate = config.public_snapshot()
    candidate.update(
        {
            "llm_provider": provider or config.llm_provider,
            "api_key": api_key,
            "model_name": model or config.model_name,
            "base_url": base_url,
        }
    )
    candidate.update({key: value for key, value in payload.items() if key in candidate})
    try:
        ALOSConfig(**candidate)
    except Exception as exc:
        errors.append(str(exc))

    return {
        "ok": not errors,
        "errors": errors,
        "provider": provider,
        "model": model,
        "base_url": base_url,
        "api_key_set": bool(api_key),
    }


def _anthropic_probe_url() -> str:
    return "https://api.anthropic.com/v1/models"


def validate_provider_connection(payload: dict, *, timeout_seconds: int = 8) -> dict[str, Any]:
    base_result = validate_provider_payload(payload)
    if not base_result["ok"]:
        return store_validation_result({
            **base_result,
            "checked_network": False,
            "status_code": None,
            "message": "Provider settings are incomplete.",
        })

    provider = base_result["provider"]
    api_key = str(payload.get("api_key") or config.api_key or "").strip()
    model = base_result["model"]

    # Build probe request per provider.
    if provider == "anthropic":
        probe_url = _anthropic_probe_url()
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
    else:
        # OpenAI-spec providers: NIM, OpenAI, Ollama, openai_compatible.
        base_url = (base_result["base_url"] or "").rstrip("/") + "/"
        probe_url = urljoin(base_url, "models")
        headers = {"Authorization": f"Bearer {api_key or 'ollama'}"}

    try:
        response = requests.get(probe_url, headers=headers, timeout=timeout_seconds)
    except requests.RequestException as exc:
        return store_validation_result({
            **base_result,
            "ok": False,
            "api_key_fingerprint": api_key_fingerprint(api_key),
            "checked_network": True,
            "status_code": None,
            "message": f"Provider endpoint could not be reached: {exc}",
        })

    if response.status_code in {401, 403}:
        return store_validation_result({
            **base_result,
            "ok": False,
            "api_key_fingerprint": api_key_fingerprint(api_key),
            "checked_network": True,
            "status_code": response.status_code,
            "message": "Provider rejected the API key.",
        })
    if response.status_code >= 400:
        return store_validation_result({
            **base_result,
            "ok": False,
            "api_key_fingerprint": api_key_fingerprint(api_key),
            "checked_network": True,
            "status_code": response.status_code,
            "message": f"Provider returned HTTP {response.status_code}.",
        })

    model_seen = True
    try:
        body = response.json()
        models = body.get("data", []) if isinstance(body, dict) else []
        ids = {item.get("id") for item in models if isinstance(item, dict)}
        model_seen = not ids or model in ids
    except Exception:
        ids = set()

    if not model_seen:
        return store_validation_result({
            **base_result,
            "ok": False,
            "api_key_fingerprint": api_key_fingerprint(api_key),
            "checked_network": True,
            "status_code": response.status_code,
            "message": f"Connected, but model '{model}' was not listed by provider.",
        })

    return store_validation_result({
        **base_result,
        "ok": True,
        "api_key_fingerprint": api_key_fingerprint(api_key),
        "checked_network": True,
        "status_code": response.status_code,
        "message": "Provider connection validated.",
    })
