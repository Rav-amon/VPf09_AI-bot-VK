"""JSON-файлы пользователей: один файл на user_id, запись через замену файла."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
from pathlib import Path
from typing import Awaitable, Callable, TypeVar

import aiofiles

from models.records import UserRecord, create_user_record, record_from_dict, record_to_dict
from utils.errors import ServiceError

T = TypeVar("T")
Mutator = Callable[[UserRecord], T | Awaitable[T]]


class JsonUserStorage:
    """Хранилище состояния. Блокировка на пользователя сериализует запись одного файла."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._directory.mkdir(parents=True, exist_ok=True)
        self._locks: dict[int, asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    async def _lock_for(self, user_id: int) -> asyncio.Lock:
        async with self._guard:
            lock = self._locks.get(user_id)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[user_id] = lock
            return lock

    def _path(self, user_id: int) -> Path:
        # bool является подклассом int, поэтому его отсекаем отдельно.
        if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
            raise ServiceError("invalid_user", "Некорректный идентификатор пользователя")
        return self._directory / f"{user_id}.json"

    async def _read(self, user_id: int) -> UserRecord | None:
        path = self._path(user_id)
        if not path.exists():
            return None
        async with aiofiles.open(path, encoding="utf-8") as file:
            raw_text = await file.read()
        try:
            raw = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ServiceError(
                "storage_corrupt",
                "Не удалось прочитать сохранённые диалоги. Файл пользователя повреждён.",
                {"user_id": user_id},
            ) from exc
        if not isinstance(raw, dict):
            raise ServiceError(
                "storage_corrupt",
                "Не удалось прочитать сохранённые диалоги. Файл пользователя повреждён.",
                {"user_id": user_id},
            )
        version = raw.get("schema_version", 1)
        if isinstance(version, int) and version > 1:
            raise ServiceError(
                "storage_version",
                "Файл пользователя создан более новой версией бота.",
                {"user_id": user_id, "schema_version": version},
            )
        return record_from_dict(raw, user_id)

    async def _write(self, record: UserRecord) -> None:
        path = self._path(record.user_id)
        temporary = path.with_suffix(".tmp")
        payload = json.dumps(record_to_dict(record), ensure_ascii=False, indent=2)
        try:
            async with aiofiles.open(temporary, "w", encoding="utf-8") as file:
                await file.write(payload)
            # os.replace подменяет файл целиком и не оставляет обрезанный JSON.
            await asyncio.to_thread(os.replace, temporary, path)
        except Exception:
            if temporary.exists():
                temporary.unlink(missing_ok=True)
            raise

    async def get(self, user_id: int) -> UserRecord | None:
        """Читает карточку или возвращает None, если пользователь ещё не писал."""
        lock = await self._lock_for(user_id)
        async with lock:
            return await self._read(user_id)

    async def ensure(self, user_id: int) -> UserRecord:
        """Создаёт карточку при первом обращении."""
        lock = await self._lock_for(user_id)
        async with lock:
            existing = await self._read(user_id)
            if existing is not None:
                return existing
            record = create_user_record(user_id)
            await self._write(record)
            return record

    async def update(self, user_id: int, mutator: Mutator[T]) -> T:
        """Меняет карточку под блокировкой и сохраняет её только при успехе."""
        lock = await self._lock_for(user_id)
        async with lock:
            record = await self._read(user_id)
            if record is None:
                raise ServiceError(
                    "user_not_found",
                    "Профиль ещё не создан. Отправьте любое сообщение.",
                    {"user_id": user_id},
                )
            result = mutator(record)
            if inspect.isawaitable(result):
                result = await result
            await self._write(record)
            return result
