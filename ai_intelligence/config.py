"""Server-only AI provider configuration."""
from pathlib import Path
import os


ALLOWED_ENV_KEYS = {
    "AI_INTELLIGENCE_PROVIDER",
    "AI_INTELLIGENCE_API_KEY",
    "AI_INTELLIGENCE_MODEL",
    "AI_INTELLIGENCE_BASE_URL",
}


def load_local_ai_environment(path=None):
    env_path = Path(path) if path else Path(__file__).resolve().parents[1] / ".env"
    if not env_path.is_file():
        return False
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in ALLOWED_ENV_KEYS or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ[key] = value
    return True


def provider_status():
    provider = os.getenv("AI_INTELLIGENCE_PROVIDER", "local").strip()
    model = os.getenv("AI_INTELLIGENCE_MODEL", "").strip()
    base_url = os.getenv("AI_INTELLIGENCE_BASE_URL", "https://api.openai.com/v1").strip()
    return {
        "provider": provider,
        "configured": provider == "openai_compatible" and bool(os.getenv("AI_INTELLIGENCE_API_KEY", "").strip()) and bool(model),
        "model": model,
        "base_url": base_url,
    }
