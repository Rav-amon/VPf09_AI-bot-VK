"""Единый формат ошибок сервисного слоя."""

from __future__ import annotations

from typing import Any


class ServiceError(Exception):
    """Ошибка с кодом, сообщением для пользователя и техническими деталями."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def as_dict(self) -> dict[str, Any]:
        """Возвращает ошибку в формате {code, message, details}."""
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }
