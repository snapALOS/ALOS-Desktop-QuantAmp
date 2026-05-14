import pytest

from src.core import config as config_module
from src.core.config import ALOSConfig, clear_provider_config, write_env_config
from src.core import llm_factory


def test_alos_config_exposes_advanced_generation_and_safety_settings():
    cfg = ALOSConfig(
        llm_provider="ollama",
        model_name="llama3.1",
        temperature=0.7,
        top_p=0.9,
        top_k=40,
        max_output_tokens=8192,
        context_window_tokens=64000,
        reserved_context_tokens=2048,
        chamber_gate_required=False,
        allow_chamber_override=False,
        autonomous_write_mode="propose_only",
    )

    snapshot = cfg.public_snapshot()

    assert snapshot["configured"] is True
    assert snapshot["temperature"] == 0.7
    assert snapshot["top_p"] == 0.9
    assert snapshot["top_k"] == 40
    assert snapshot["max_output_tokens"] == 8192
    assert snapshot["context_window_tokens"] == 64000
    assert snapshot["reserved_context_tokens"] == 2048
    assert snapshot["chamber_gate_required"] is False
    assert snapshot["allow_chamber_override"] is False
    assert snapshot["autonomous_write_mode"] == "propose_only"


@pytest.mark.parametrize(
    "field,value",
    [
        ("temperature", 2.1),
        ("top_p", 0),
        ("top_k", 0),
        ("max_output_tokens", 0),
        ("presence_penalty", 2.1),
        ("autonomous_write_mode", "reckless"),
    ],
)
def test_alos_config_rejects_invalid_advanced_settings(field, value):
    with pytest.raises(ValueError):
        ALOSConfig(llm_provider="ollama", model_name="llama3.1", **{field: value})


def test_write_and_clear_provider_config_preserves_runtime_knobs(tmp_path, monkeypatch):
    original = {
        field: getattr(config_module.config, field)
        for field in type(config_module.config).model_fields
    }
    monkeypatch.setattr(config_module, "ENV_PATH", tmp_path / ".env")

    try:
        updated = write_env_config(
            {
                "llm_provider": "openai",
                "api_key": "sk-test-value",
                "model_name": "gpt-test",
                "temperature": 0.6,
                "top_p": 0.92,
                "top_k": 25,
                "max_output_tokens": 6000,
                "context_window_tokens": 50000,
                "reserved_context_tokens": 3000,
                "chamber_gate_required": False,
                "allow_chamber_override": False,
                "autonomous_write_mode": "manual_only",
            }
        )
        assert updated.temperature == 0.6
        assert updated.top_k == 25
        assert updated.allow_chamber_override is False

        cleared = clear_provider_config()
        assert cleared.api_key == ""
        assert cleared.is_configured() is False
        assert cleared.temperature == 0.6
        assert cleared.allow_chamber_override is False
    finally:
        for field, value in original.items():
            setattr(config_module.config, field, value)


def test_llm_factory_applies_generation_settings_to_openai_compatible_model(monkeypatch):
    class DummyChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(llm_factory, "ChatOpenAI", DummyChatOpenAI)
    monkeypatch.setattr(llm_factory.config, "llm_provider", "nvidia")
    monkeypatch.setattr(llm_factory.config, "api_key", "sk-test-value")
    monkeypatch.setattr(llm_factory.config, "model_name", "test-model")
    monkeypatch.setattr(llm_factory.config, "base_url", "https://example.test/v1")
    monkeypatch.setattr(llm_factory.config, "max_retries", 2)
    monkeypatch.setattr(llm_factory.config, "timeout_seconds", 15)
    monkeypatch.setattr(llm_factory.config, "temperature", 0.35)
    monkeypatch.setattr(llm_factory.config, "top_p", 0.88)
    monkeypatch.setattr(llm_factory.config, "top_k", 30)
    monkeypatch.setattr(llm_factory.config, "max_output_tokens", 1234)
    monkeypatch.setattr(llm_factory.config, "presence_penalty", 0.1)
    monkeypatch.setattr(llm_factory.config, "frequency_penalty", 0.2)
    monkeypatch.setattr(llm_factory.config, "seed", 42)

    model = llm_factory.get_llm()

    assert model.kwargs["temperature"] == 0.35
    assert model.kwargs["max_tokens"] == 1234
    assert model.kwargs["model_kwargs"] == {
        "top_p": 0.88,
        "presence_penalty": 0.1,
        "frequency_penalty": 0.2,
        "seed": 42,
        "top_k": 30,
    }
