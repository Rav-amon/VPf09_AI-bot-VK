"""Точка входа. Запускает long poll сообщества ВКонтакте."""

from __future__ import annotations

from bot.factory import create_bot
from config.settings import load_settings
from utils.errors import ServiceError
from utils.logging_setup import setup_logging


def main() -> None:
    """Читает окружение и передаёт управление циклу VKBottle."""
    try:
        settings = load_settings()
    except ServiceError as exc:
        print(exc.message)
        raise SystemExit(1) from exc
    setup_logging(settings.log_level)
    bot = create_bot(settings)
    # run() — актуальный запуск VKBottle 4.11. Сами обработчики остаются асинхронными.
    bot.run()


if __name__ == "__main__":
    main()
