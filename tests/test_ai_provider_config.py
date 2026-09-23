from ai_intelligence.config import load_local_ai_environment, provider_status


def test_local_ai_environment_loads_only_ai_keys_without_overriding(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_INTELLIGENCE_MODEL", "host-model")
    monkeypatch.delenv("AI_INTELLIGENCE_PROVIDER", raising=False)
    monkeypatch.delenv("AI_INTELLIGENCE_API_KEY", raising=False)
    monkeypatch.delenv("AI_INTELLIGENCE_BASE_URL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "AI_INTELLIGENCE_PROVIDER=openai_compatible\n"
        "AI_INTELLIGENCE_API_KEY='server-secret'\n"
        "AI_INTELLIGENCE_MODEL=file-model\n"
        "AI_INTELLIGENCE_BASE_URL=https://api.openai.com/v1\n"
        "SECRET_KEY=must-not-load\n",
        encoding="utf-8",
    )

    assert load_local_ai_environment(env_file) is True
    assert provider_status() == {
        "provider": "openai_compatible",
        "configured": True,
        "model": "host-model",
        "base_url": "https://api.openai.com/v1",
    }
    assert "SECRET_KEY" not in __import__("os").environ
