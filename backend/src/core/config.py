import logging
import os
import sys
from contextvars import ContextVar
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator

# Supported LLM providers. Each maps to a dispatch branch in llm_factory.
SUPPORTED_PROVIDERS = {"nvidia", "openai", "anthropic", "ollama", "openai_compatible"}

# Sensible per-provider defaults applied when the user leaves base_url blank.
PROVIDER_DEFAULT_BASE_URL = {
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "openai": None,  # SDK default
    "anthropic": None,  # SDK default
    "ollama": "http://localhost:11434/v1",
    "openai_compatible": None,  # user must supply
}

PROVIDER_DEFAULT_MODEL = {
    "nvidia": "nvidia/nemotron-3-super-120b-a12b",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-5",
    "ollama": "llama3.1",
    "openai_compatible": "",
}

# ROOT_DIR is the backend source tree. It must stay pointed at the code
# because tool execution, policy guards, and workspace-relative paths all
# resolve against it. User-mutable state lives under USER_DATA_DIR instead
# — see ALOS_DATA_DIR below.
ROOT_DIR = Path(__file__).parent.parent.parent.resolve()


def _default_user_data_dir() -> Path:
    """Platform-appropriate default for user state when ALOS_DATA_DIR isn't set."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "com.alos.desktop"
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "com.alos.desktop"
    xdg = os.environ.get("XDG_DATA_HOME")
    return Path(xdg) / "alos-desktop" if xdg else Path.home() / ".local" / "share" / "alos-desktop"


# USER_DATA_DIR is where every piece of mutable per-user state lives:
# the .env with provider credentials, logs, memory/chroma, SQLite DB,
# bootstrap key, patch inbox, setup_status.json, etc.
#
# Resolution order:
#   1. ALOS_DATA_DIR env var — set by the Rust sidecar for packaged apps.
#   2. Platform default (~/Library/Application Support/com.alos.desktop on macOS).
#   3. Fallback: {ROOT_DIR} — dev-mode behavior when running the backend
#      standalone without the Tauri shell. Keeps local dev self-contained.
_env_data_dir = os.environ.get("ALOS_DATA_DIR", "").strip()
if _env_data_dir:
    USER_DATA_DIR = Path(_env_data_dir).expanduser().resolve()
elif os.environ.get("ALOS_USE_PROJECT_DATA") == "1":
    USER_DATA_DIR = ROOT_DIR
elif (ROOT_DIR / "pyproject.toml").is_file():
    # Dev mode: running uvicorn directly from the backend source tree. Keep
    # state colocated with the code for easy inspection and cleanup.
    USER_DATA_DIR = ROOT_DIR
else:
    # Packaged layout with no explicit override — fall back to the platform
    # default. (In practice the Tauri sidecar always sets ALOS_DATA_DIR, so
    # this branch is the safety net for edge cases.)
    USER_DATA_DIR = _default_user_data_dir()

LOGS_DIR = USER_DATA_DIR / "logs"
MEMORY_DIR = USER_DATA_DIR / "memory"
ENV_PATH = USER_DATA_DIR / ".env"
DATA_DIR = USER_DATA_DIR / "data"

# Ensure explicit directory structures exist beforehand
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
MEMORY_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

log_session_id: ContextVar[str] = ContextVar("alos_log_session_id", default="-")


def set_log_session(session_id: str):
    """Bind subsequent log records in this async context to one ALOS session."""
    return log_session_id.set(session_id or "-")


def reset_log_session(token) -> None:
    log_session_id.reset(token)


_record_factory = logging.getLogRecordFactory()


def _alos_record_factory(*args, **kwargs):
    record = _record_factory(*args, **kwargs)
    record.alos_session_id = log_session_id.get()
    return record


logging.setLogRecordFactory(_alos_record_factory)

def setup_global_logging():
    """
    Configures robust logging directed to both the console and a persistent file.
    Enforces the 'NEVER GUESS! LOG AND CONFIRM' operational constraint.
    """
    logger = logging.getLogger("ALOS")
    logger.setLevel(logging.DEBUG)
    
    # Prevent duplicate handlers if the runtime reloads
    if not logger.handlers:
        fh = logging.FileHandler(LOGS_DIR / "system.log", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - session=%(alos_session_id)s - [%(filename)s:%(lineno)d] - %(message)s'
        )
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)
        
        logger.addHandler(fh)
        logger.addHandler(ch)
    
    return logger

system_logger = setup_global_logging()

class ALOSConfig(BaseSettings):
    """
    Exhaustive type-checked configuration for the ALOS backend.
    """
    llm_provider: str = Field(default="nvidia", description="The overarching LLM provider")
    api_key: str = Field(default="", description="API Access key for provider endpoints")
    model_name: str = Field(default="nvidia/nemotron-3-super-120b-a12b", description="Precise model endpoint identifier")
    base_url: Optional[str] = Field(default=None, description="Optional custom base URL for OpenAI-spec wrapper compatability")
    max_retries: int = Field(default=3, description="Maximum API retry attempts on transient failures")
    timeout_seconds: int = Field(default=120, description="Hard timeout threshold for inferences")

    temperature: float = Field(default=0.2, description="Sampling temperature for model responses")
    top_p: float = Field(default=1.0, description="Nucleus sampling threshold")
    top_k: Optional[int] = Field(default=None, description="Optional top-k sampling cap for providers that support it")
    max_output_tokens: int = Field(default=4096, description="Maximum tokens the model may generate")
    context_window_tokens: int = Field(default=128000, description="Advertised context window used for planning budgets")
    max_input_tokens: Optional[int] = Field(default=None, description="Optional hard input-token budget before reserved space")
    reserved_context_tokens: int = Field(default=4096, description="Context budget reserved for tool/results/system overhead")
    presence_penalty: float = Field(default=0.0, description="Provider presence penalty when supported")
    frequency_penalty: float = Field(default=0.0, description="Provider frequency penalty when supported")
    seed: Optional[int] = Field(default=None, description="Optional deterministic sampling seed when supported")

    max_agent_turns: int = Field(default=250, description="Maximum orchestration cycles per agent run before the logic guard halts the run")

    chamber_gate_required: bool = Field(default=True, description="Require Chamber build/test evidence before writes")
    allow_chamber_override: bool = Field(default=True, description="Allow authenticated users to override failed Chamber gates")
    autonomous_write_mode: str = Field(default="chamber_gated", description="Default policy posture for autonomous writes")

    @field_validator("llm_provider")
    @classmethod
    def _validate_provider(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported llm_provider '{v}'. Must be one of: {sorted(SUPPORTED_PROVIDERS)}"
            )
        return v

    @field_validator("temperature")
    @classmethod
    def _validate_temperature(cls, v: float) -> float:
        if not 0 <= v <= 2:
            raise ValueError("temperature must be between 0 and 2")
        return v

    @field_validator("top_p")
    @classmethod
    def _validate_top_p(cls, v: float) -> float:
        if not 0 < v <= 1:
            raise ValueError("top_p must be greater than 0 and no more than 1")
        return v

    @field_validator("top_k", "max_input_tokens", "seed")
    @classmethod
    def _validate_optional_positive_int(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 1:
            raise ValueError("optional integer settings must be greater than 0")
        return v

    @field_validator("max_retries", "timeout_seconds", "max_output_tokens", "context_window_tokens", "reserved_context_tokens", "max_agent_turns")
    @classmethod
    def _validate_positive_int(cls, v: int) -> int:
        if v < 1:
            raise ValueError("integer settings must be greater than 0")
        return v

    @field_validator("presence_penalty", "frequency_penalty")
    @classmethod
    def _validate_penalty(cls, v: float) -> float:
        if not -2 <= v <= 2:
            raise ValueError("penalties must be between -2 and 2")
        return v

    @field_validator("autonomous_write_mode")
    @classmethod
    def _validate_autonomous_write_mode(cls, v: str) -> str:
        v = (v or "").strip().lower()
        allowed = {"manual_only", "propose_only", "chamber_gated", "autonomous"}
        if v not in allowed:
            raise ValueError(f"autonomous_write_mode must be one of: {sorted(allowed)}")
        return v

    def resolved_base_url(self) -> Optional[str]:
        """Return the base_url the provider should use, falling back to provider default."""
        if self.base_url and self.base_url.strip():
            return self.base_url.strip()
        return PROVIDER_DEFAULT_BASE_URL.get(self.llm_provider)
    
    def is_configured(self) -> bool:
        if not self.model_name.strip():
            return False
        # Ollama runs locally and typically doesn't require an API key.
        if self.llm_provider == "ollama":
            return True
        # openai_compatible requires a base_url to know where to talk.
        if self.llm_provider == "openai_compatible" and not (self.base_url and self.base_url.strip()):
            return False
        return bool(self.api_key and len(self.api_key.strip()) >= 10)

    def public_snapshot(self) -> dict:
        return {
            "configured": self.is_configured(),
            "llm_provider": self.llm_provider,
            "model_name": self.model_name,
            "base_url": self.base_url or "",
            "max_retries": self.max_retries,
            "timeout_seconds": self.timeout_seconds,
            "api_key_set": bool(self.api_key),
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "max_output_tokens": self.max_output_tokens,
            "context_window_tokens": self.context_window_tokens,
            "max_input_tokens": self.max_input_tokens,
            "reserved_context_tokens": self.reserved_context_tokens,
            "presence_penalty": self.presence_penalty,
            "frequency_penalty": self.frequency_penalty,
            "seed": self.seed,
            "max_agent_turns": self.max_agent_turns,
            "chamber_gate_required": self.chamber_gate_required,
            "allow_chamber_override": self.allow_chamber_override,
            "autonomous_write_mode": self.autonomous_write_mode,
        }

    def openai_model_kwargs(self) -> dict:
        kwargs = {
            "top_p": self.top_p,
            "presence_penalty": self.presence_penalty,
            "frequency_penalty": self.frequency_penalty,
        }
        if self.seed is not None:
            kwargs["seed"] = self.seed
        if self.top_k is not None and self.llm_provider != "openai":
            kwargs["top_k"] = self.top_k
        return kwargs

    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore"
    )

def _payload_value(payload: dict, key: str, current, *, keep_blank: bool = False):
    if key not in payload:
        return current
    value = payload.get(key)
    if value is None:
        return "" if keep_blank else current
    if isinstance(value, str):
        text = value.strip()
        return text if (text or keep_blank) else current
    return value


def _optional_int_payload(payload: dict, key: str, current: Optional[int]) -> Optional[int]:
    if key not in payload:
        return current
    value = payload.get(key)
    if value in (None, ""):
        return None
    return int(value)


def _bool_payload(payload: dict, key: str, current: bool) -> bool:
    if key not in payload:
        return current
    value = payload.get(key)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _persist_env_values(values: dict[str, object]) -> None:
    lines = ["# ALOS guided setup configuration"]
    for key, value in values.items():
        if value is None:
            continue
        escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{key}="{escaped}"')
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _refresh_global_config() -> ALOSConfig:
    updated = ALOSConfig(_env_file=str(ENV_PATH))
    for field_name in type(updated).model_fields:
        setattr(config, field_name, getattr(updated, field_name))
    return config


def _env_values_from_payload(payload: dict, current: ALOSConfig, *, clear_provider: bool = False) -> dict[str, object]:
    provider = "nvidia" if clear_provider else str(_payload_value(payload, "llm_provider", current.llm_provider) or "nvidia").strip()
    model = (
        PROVIDER_DEFAULT_MODEL.get(provider, "")
        if clear_provider
        else str(_payload_value(payload, "model_name", current.model_name)).strip()
    )
    api_key = "" if clear_provider else str(payload.get("api_key") or current.api_key or "").strip()
    base_url = "" if clear_provider else str(_payload_value(payload, "base_url", current.base_url or "", keep_blank=True)).strip()

    return {
        "LLM_PROVIDER": provider,
        "API_KEY": api_key,
        "MODEL_NAME": model,
        "BASE_URL": base_url,
        "MAX_RETRIES": int(_payload_value(payload, "max_retries", current.max_retries)),
        "TIMEOUT_SECONDS": int(_payload_value(payload, "timeout_seconds", current.timeout_seconds)),
        "TEMPERATURE": float(_payload_value(payload, "temperature", current.temperature)),
        "TOP_P": float(_payload_value(payload, "top_p", current.top_p)),
        "TOP_K": _optional_int_payload(payload, "top_k", current.top_k),
        "MAX_OUTPUT_TOKENS": int(_payload_value(payload, "max_output_tokens", current.max_output_tokens)),
        "CONTEXT_WINDOW_TOKENS": int(_payload_value(payload, "context_window_tokens", current.context_window_tokens)),
        "MAX_INPUT_TOKENS": _optional_int_payload(payload, "max_input_tokens", current.max_input_tokens),
        "RESERVED_CONTEXT_TOKENS": int(_payload_value(payload, "reserved_context_tokens", current.reserved_context_tokens)),
        "PRESENCE_PENALTY": float(_payload_value(payload, "presence_penalty", current.presence_penalty)),
        "FREQUENCY_PENALTY": float(_payload_value(payload, "frequency_penalty", current.frequency_penalty)),
        "SEED": _optional_int_payload(payload, "seed", current.seed),
        "MAX_AGENT_TURNS": int(_payload_value(payload, "max_agent_turns", current.max_agent_turns)),
        "CHAMBER_GATE_REQUIRED": str(_bool_payload(payload, "chamber_gate_required", current.chamber_gate_required)).lower(),
        "ALLOW_CHAMBER_OVERRIDE": str(_bool_payload(payload, "allow_chamber_override", current.allow_chamber_override)).lower(),
        "AUTONOMOUS_WRITE_MODE": str(_payload_value(payload, "autonomous_write_mode", current.autonomous_write_mode)).strip(),
    }


def write_env_config(payload: dict) -> ALOSConfig:
    """
    Persist guided setup settings without requiring a terminal session.
    Blank api_key means "keep the existing configured key".
    """
    current = ALOSConfig(_env_file=str(ENV_PATH))
    _persist_env_values(_env_values_from_payload(payload, current))
    _refresh_global_config()
    system_logger.info(f"Configuration updated. Provider: '{config.llm_provider}' | Model: '{config.model_name}'")
    return config


def clear_provider_config() -> ALOSConfig:
    """Clear provider credentials/model selection while preserving safety/runtime knobs."""
    current = ALOSConfig(_env_file=str(ENV_PATH))
    _persist_env_values(_env_values_from_payload({}, current, clear_provider=True))
    _refresh_global_config()
    system_logger.info("Provider configuration cleared from guided setup.")
    return config


config = ALOSConfig()
if config.is_configured():
    system_logger.info(f"Configuration loaded. Provider: '{config.llm_provider}' | Model: '{config.model_name}'")
else:
    system_logger.warning("ALOS provider is not configured yet. Guided setup remains available in the web UI.")
