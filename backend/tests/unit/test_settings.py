import pytest
from codeweave.config.settings import Settings

def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host:5432/db")
    monkeypatch.setenv("REDIS_URL", "redis://host:6379/0")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.test.com/v1")
    monkeypatch.setenv("MODEL_NAME", "test-model")

    s = Settings()
    assert s.database_url == "postgresql://user:pass@host:5432/db"
    assert s.redis_url == "redis://host:6379/0"
    assert s.model_name == "test-model"

def test_settings_has_defaults(monkeypatch):
    """openai_api_key 是必填项,测试时也必须设置。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    s = Settings(_env_file=None)
    assert s.compact_threshold == 32000
    assert s.compact_enabled is True
    assert s.plan_mode_default is True
    assert s.model_name == "deepseek-v4-flash"
