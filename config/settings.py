"""Настройки из окружения. Секреты не имеют значений по умолчанию."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from utils.errors import ServiceError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_BASE_URL = "https://api.proxyapi.ru"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_OUTPUT_TOKENS = 2048
MIN_OUTPUT_TOKENS = 128
MAX_OUTPUT_TOKENS = 8192
REQUEST_TIMEOUT_MS = 60_000


@dataclass(frozen=True, slots=True)
class Settings:
    """Параметры процесса. Ключи остаются только в окружении."""

    vk_token: str
    proxy_api_key: str
    gemini_model: str
    gemini_base_url: str
    temperature: float
    max_output_tokens: int
    log_level: str
    users_dir: Path
    ai_provider: str = "gemini"
    request_timeout_ms: int = REQUEST_TIMEOUT_MS


def load_env_files(root: Path | None = None) -> None:
    """Читает .env проекта, а если его нет — запасной файл в .cursor/rules."""
    project_root = root or PROJECT_ROOT
    # override=False: уже заданное окружение важнее файла, корневой .env важнее запасного.
    load_dotenv(project_root / ".env", override=False)
    load_dotenv(project_root / ".cursor" / "rules" / ".env", override=False)


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ServiceError(
            "config_error",
            f"Не задана переменная окружения {name}. Скопируйте .env.example в .env.",
        )
    return value


def _temperature() -> float:
    raw = os.getenv("GEMINI_TEMPERATURE", str(DEFAULT_TEMPERATURE)).strip()
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_TEMPERATURE
    if value < 0 or value > 2:
        return DEFAULT_TEMPERATURE
    return value


def _max_tokens() -> int:
    raw = os.getenv("GEMINI_MAX_OUTPUT_TOKENS", str(DEFAULT_MAX_OUTPUT_TOKENS)).strip()
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_OUTPUT_TOKENS
    if value < MIN_OUTPUT_TOKENS or value > MAX_OUTPUT_TOKENS:
        return DEFAULT_MAX_OUTPUT_TOKENS
    return value


def load_settings(root: Path | None = None) -> Settings:
    """Собирает настройки. Падает до запуска бота, если нет токена или ключа."""
    project_root = root or PROJECT_ROOT
    load_env_files(project_root)
    users_dir = project_root / "users"
    return Settings(
        vk_token=_required("VK_TOKEN"),
        proxy_api_key=_required("PROXY_API_KEY"),
        gemini_model=os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        gemini_base_url=(
            os.getenv("GEMINI_BASE_URL", DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL
        ).rstrip("/"),
        temperature=_temperature(),
        max_output_tokens=_max_tokens(),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
        users_dir=users_dir,
        ai_provider=os.getenv("AI_PROVIDER", "gemini").strip().lower() or "gemini",
    )
