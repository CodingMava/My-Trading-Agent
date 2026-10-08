"""Runtime settings.

Secrets come only from environment variables, optionally loaded from a git-ignored ``.env`` file.
Everything else comes from ``config/settings.toml``. Secrets are wrapped in :class:`Secret` so they
can't leak through a repr, an f-string or a log line by accident.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
ENV_FILE = ROOT / ".env"
SETTINGS_FILE = CONFIG_DIR / "settings.toml"
SUPPORTED_AI_PROVIDERS = ("gemini",)


class Secret:
    """A string that refuses to print itself. Call ``reveal()`` only at the point of use."""

    __slots__ = ("_value",)

    def __init__(self, value: str | None):
        self._value = (value or "").strip()

    def reveal(self) -> str:
        return self._value

    def __bool__(self) -> bool:
        return bool(self._value)

    def __repr__(self) -> str:
        return "Secret('***')" if self._value else "Secret('')"

    __str__ = __repr__


def parse_env_file(path: Path) -> dict[str, str]:
    """Minimal .env parser: KEY=VALUE lines, '#' comments, optional quotes and 'export ' prefix."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            values[key] = value
    return values


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: Secret
    telegram_chat_id: str
    gemini_api_key: Secret
    telegram_enabled: bool  # config flag AND credentials present
    telegram_timeout_seconds: float
    ai_enabled: bool  # config flag AND key present AND provider supported
    ai_provider: str
    ai_model: str
    ai_timeout_seconds: float
    warnings: tuple[str, ...] = ()

    def secret_values(self) -> list[str]:
        """Raw secret strings, for log redaction only."""
        return [s.reveal() for s in (self.telegram_bot_token, self.gemini_api_key) if s]


def load_settings(env: dict[str, str] | None = None, settings_file: Path = SETTINGS_FILE,
                  env_file: Path = ENV_FILE) -> Settings:
    """Real environment variables take precedence over values in the .env file."""
    if env is None:
        env = {**parse_env_file(env_file), **os.environ}
    with open(settings_file, "rb") as fh:
        cfg = tomllib.load(fh)
    notifications, ai = cfg.get("notifications", {}), cfg.get("ai", {})

    token = Secret(env.get("TELEGRAM_BOT_TOKEN"))
    chat_id = (env.get("TELEGRAM_CHAT_ID") or "").strip()
    gemini_key = Secret(env.get("GEMINI_API_KEY"))
    warnings = []

    telegram_enabled = bool(notifications.get("telegram_enabled", True))
    if telegram_enabled and not (token and chat_id):
        telegram_enabled = False
        warnings.append("Telegram is off: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are not set (see .env.example).")

    ai_provider = str(ai.get("provider", "gemini"))
    ai_enabled = bool(ai.get("enabled", False))
    if ai_enabled and ai_provider not in SUPPORTED_AI_PROVIDERS:
        ai_enabled = False
        warnings.append(f"AI is off: provider {ai_provider!r} is not supported yet.")
    if ai_enabled and not gemini_key:
        ai_enabled = False
        warnings.append("AI is off: GEMINI_API_KEY is not set (see .env.example).")

    return Settings(
        telegram_bot_token=token,
        telegram_chat_id=chat_id,
        gemini_api_key=gemini_key,
        telegram_enabled=telegram_enabled,
        telegram_timeout_seconds=float(notifications.get("telegram_timeout_seconds", 10)),
        ai_enabled=ai_enabled,
        ai_provider=ai_provider,
        ai_model=str(ai.get("model", "gemini-2.5-flash")),
        ai_timeout_seconds=float(ai.get("timeout_seconds", 20)),
        warnings=tuple(warnings),
    )
