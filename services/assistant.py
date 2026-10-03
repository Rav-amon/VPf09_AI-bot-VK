"""Сценарии меню: тексты для пользователя без вызовов VK API."""

from __future__ import annotations

import math

from models.commands import Cmd, Screen
from models.records import MAX_HISTORY_MESSAGES, Dialog, UserRecord, active_dialog
from models.roles import get_role, list_roles
from models.screen import DialogView, ScreenResponse
from services.ai_service import AIService
from services.chat_service import ChatService
from services.dialog_service import MAX_DIALOGS, DialogService, is_dialog_id
from utils.errors import ServiceError

DIALOGS_PER_PAGE = 4


class AssistantApp:
    """Прикладные сценарии бота. Обработчики VK только показывают результат."""

    def __init__(
        self,
        dialogs: DialogService,
        chat: ChatService,
        ai: AIService,
    ) -> None:
        self._dialogs = dialogs
        self._chat = chat
        self._ai = ai

    async def open_main(self, user_id: int) -> ScreenResponse:
        """Главный экран с активным диалогом."""
        record = await self._dialogs.ensure_user(user_id)
        return self._screen(record, self._main_text(record), Screen.MAIN)

    async def open_help(self, user_id: int) -> ScreenResponse:
        """Короткая справка обычным языком."""
        record = await self._dialogs.ensure_user(user_id)
        text = (
            "Я помогаю отвечать на вопросы прямо в переписке.\n\n"
            "Кнопки внизу:\n"
            "• Новый диалог — отдельная тема с чистой историей\n"
            "• Список диалогов — открыть, переименовать или удалить\n"
            "• Настройки — модель и очистка истории\n"
            "• Помощь — это сообщение\n\n"
            f"{self._roles_catalog(active_dialog(record).role)}\n\n"
            "Просто напишите вопрос. Я помню до "
            f"{MAX_HISTORY_MESSAGES} последних сообщений в каждом диалоге. "
            "Картинки и голосовые пока не разбираю."
        )
        return self._screen(record, text, Screen.HELP)

    async def open_settings(self, user_id: int) -> ScreenResponse:
        """Настройки текущего диалога и сведения о модели."""
        record = await self._dialogs.ensure_user(user_id)
        return ScreenResponse(text=self._settings_text(record), screen=Screen.SETTINGS)

    async def open_roles(self, user_id: int) -> ScreenResponse:
        """Список режимов. Выбор применится только к активному диалогу."""
        record = await self._dialogs.ensure_user(user_id)
        dialog = active_dialog(record)
        text = (
            f"Диалог «{dialog.title}».\n"
            "Новый режим изменит стиль следующих ответов. История сохранится.\n\n"
            f"{self._roles_catalog(dialog.role)}"
        )
        return self._screen(record, text, Screen.ROLES)

    async def open_dialogs(self, user_id: int, page: int = 0) -> ScreenResponse:
        """Страница списка диалогов."""
        record = await self._dialogs.ensure_user(user_id)
        return self._dialogs_screen(record, page)

    async def open_dialog(self, user_id: int, dialog_id: str) -> ScreenResponse:
        """Переключает активный диалог и показывает его карточку."""
        if not is_dialog_id(dialog_id):
            record = await self._dialogs.ensure_user(user_id)
            return self._dialogs_screen(record, 0, prefix="Такого диалога нет.\n\n")
        try:
            record = await self._dialogs.switch_dialog(user_id, dialog_id)
        except ServiceError as exc:
            record = await self._dialogs.get_record(user_id)
            return self._dialogs_screen(record, 0, prefix=f"{exc.message}\n\n")
        return self._dialog_screen(record, dialog_id)

    async def create_dialog(self, user_id: int) -> ScreenResponse:
        """Создаёт диалог в режиме обычного помощника."""
        try:
            record = await self._dialogs.create_dialog(user_id)
        except ServiceError as exc:
            record = await self._dialogs.get_record(user_id)
            return self._dialogs_screen(record, 0, prefix=f"{exc.message}\n\n")
        dialog = active_dialog(record)
        text = (
            f"Создан диалог «{dialog.title}».\n"
            "История пустая, режим — обычный помощник. Напишите первое сообщение."
        )
        return ScreenResponse(
            text=text,
            screen=Screen.DIALOG,
            dialog_id=dialog.id,
            role_id=dialog.role,
        )

    async def ask_rename(self, user_id: int, dialog_id: str) -> ScreenResponse:
        """Просит прислать новое название одним сообщением."""
        record = await self._dialogs.ensure_user(user_id)
        try:
            dialog = self._dialogs.find_dialog(record, dialog_id)
        except ServiceError as exc:
            return self._dialogs_screen(record, 0, prefix=f"{exc.message}\n\n")
        text = (
            f"Напишите новое название для диалога «{dialog.title}» одним сообщением.\n"
            "Или нажмите «Отмена»."
        )
        return ScreenResponse(text=text, screen=Screen.CANCEL, dialog_id=dialog.id)

    async def rename(self, user_id: int, dialog_id: str, title: str) -> ScreenResponse:
        """Сохраняет название и возвращает карточку диалога."""
        record = await self._dialogs.rename_dialog(user_id, dialog_id, title)
        dialog = self._dialogs.find_dialog(record, dialog_id)
        text = f"Диалог переименован в «{dialog.title}».\n\n{self._dialog_body(dialog)}"
        return ScreenResponse(
            text=text,
            screen=Screen.DIALOG,
            dialog_id=dialog.id,
            role_id=dialog.role,
        )

    async def ask_delete(self, user_id: int, dialog_id: str) -> ScreenResponse:
        """Просит подтвердить удаление."""
        record = await self._dialogs.ensure_user(user_id)
        try:
            dialog = self._dialogs.find_dialog(record, dialog_id)
        except ServiceError as exc:
            return self._dialogs_screen(record, 0, prefix=f"{exc.message}\n\n")
        text = (
            f"Удалить диалог «{dialog.title}»?\n"
            "История этого диалога исчезнет. Восстановить её будет нельзя."
        )
        return ScreenResponse(
            text=text,
            screen=Screen.CONFIRM,
            dialog_id=dialog.id,
            confirm_cmd=Cmd.DELETE,
        )

    async def delete_dialog(self, user_id: int, dialog_id: str) -> ScreenResponse:
        """Удаляет диалог и показывает обновлённый список."""
        _record, note = await self._dialogs.delete_dialog(user_id, dialog_id)
        record = await self._dialogs.get_record(user_id)
        return self._dialogs_screen(record, 0, prefix=f"{note}\n\n")

    async def set_role(self, user_id: int, role_id: str) -> ScreenResponse:
        """Включает режим на текущем диалоге."""
        record = await self._dialogs.set_role(user_id, role_id)
        dialog = active_dialog(record)
        role = get_role(dialog.role)
        text = (
            f"В диалоге «{dialog.title}» теперь режим «{role.title}».\n"
            "Следующие ответы будут в этом стиле. История сохранена.\n\n"
            f"{self._roles_catalog(role.id)}"
        )
        return self._screen(record, text, Screen.ROLES)

    async def ask_clear(self, user_id: int) -> ScreenResponse:
        """Просит подтвердить очистку истории."""
        record = await self._dialogs.ensure_user(user_id)
        dialog = active_dialog(record)
        text = (
            f"Очистить историю диалога «{dialog.title}»?\n"
            "Название и режим останутся. Сообщения будут удалены."
        )
        return ScreenResponse(
            text=text,
            screen=Screen.CONFIRM,
            dialog_id=dialog.id,
            confirm_cmd=Cmd.CLEAR,
        )

    async def clear_history(self, user_id: int, dialog_id: str) -> ScreenResponse:
        """Очищает историю активного диалога."""
        record = await self._dialogs.clear_history(user_id, dialog_id)
        return ScreenResponse(
            text=f"История очищена.\n\n{self._settings_text(record)}",
            screen=Screen.SETTINGS,
        )

    async def ask(self, user_id: int, text: str) -> ScreenResponse:
        """Отправляет текст в модель. Ошибка API становится понятной фразой."""
        try:
            answer = await self._chat.answer(user_id, text)
        except ServiceError as exc:
            record = await self._dialogs.ensure_user(user_id)
            return self._screen(record, exc.message, Screen.MAIN)
        record = await self._dialogs.get_record(user_id)
        return self._screen(record, answer, Screen.MAIN)

    def _main_text(self, record: UserRecord) -> str:
        dialog = active_dialog(record)
        role = get_role(dialog.role)
        fresh = (
            len(record.dialogs) == 1
            and dialog.title == "Основной"
            and not dialog.messages
        )
        intro = ""
        if fresh:
            intro = (
                "Здравствуйте. Я AI-помощник. Можно вести несколько диалогов "
                "и менять стиль общения.\n\n"
            )
        return (
            f"{intro}"
            f"Активный диалог: «{dialog.title}»\n"
            f"Режим: {role.title}\n"
            f"Сообщений в памяти: {len(dialog.messages)} из {MAX_HISTORY_MESSAGES}\n\n"
            "Нажмите кнопку под этим сообщением или напишите вопрос.\n\n"
            f"{self._roles_catalog(role.id)}"
        )

    def _settings_text(self, record: UserRecord) -> str:
        dialog = active_dialog(record)
        role = get_role(dialog.role)
        return (
            f"Модель: {self._ai.model_name}\n"
            "Подключение: ProxyAPI, формат Gemini\n"
            f"Активный диалог: «{dialog.title}»\n"
            f"Режим: {role.title}\n"
            f"Сообщений в памяти: {len(dialog.messages)} из {MAX_HISTORY_MESSAGES}\n"
            f"Диалогов: {len(record.dialogs)} из {MAX_DIALOGS}"
        )

    def _screen(self, record: UserRecord, text: str, screen: str) -> ScreenResponse:
        """Экран с идентификатором режима, чтобы клавиатура отметила текущую кнопку."""
        return ScreenResponse(text=text, screen=screen, role_id=active_dialog(record).role)

    def _roles_catalog(self, current_role_id: str) -> str:
        """Список из пяти режимов прямо в тексте сообщения."""
        lines = ["Режимы общения:"]
        for index, role in enumerate(list_roles(), start=1):
            mark = " — сейчас включён" if role.id == current_role_id else ""
            lines.append(f"{index}. {role.title}{mark}")
        lines.append("Нажмите название режима на кнопке под сообщением.")
        return "\n".join(lines)

    def _dialog_body(self, dialog: Dialog) -> str:
        role = get_role(dialog.role)
        return (
            f"Диалог: «{dialog.title}»\n"
            f"Режим: {role.title}\n"
            f"Сообщений: {len(dialog.messages)} из {MAX_HISTORY_MESSAGES}\n\n"
            "Напишите сообщение, чтобы продолжить этот диалог."
        )

    def _dialog_screen(self, record: UserRecord, dialog_id: str) -> ScreenResponse:
        dialog = self._dialogs.find_dialog(record, dialog_id)
        return ScreenResponse(
            text=self._dialog_body(dialog),
            screen=Screen.DIALOG,
            dialog_id=dialog.id,
            role_id=dialog.role,
        )

    def _dialogs_screen(
        self,
        record: UserRecord,
        page: int,
        prefix: str = "",
    ) -> ScreenResponse:
        total_pages = max(1, math.ceil(len(record.dialogs) / DIALOGS_PER_PAGE))
        current_page = min(max(page, 0), total_pages - 1)
        start = current_page * DIALOGS_PER_PAGE
        chunk = record.dialogs[start : start + DIALOGS_PER_PAGE]
        views = tuple(
            DialogView(
                id=dialog.id,
                title=dialog.title,
                role_id=dialog.role,
                role_title=get_role(dialog.role).title,
                is_active=dialog.id == record.active_dialog_id,
                message_count=len(dialog.messages),
            )
            for dialog in chunk
        )
        lines = [f"Ваши диалоги, страница {current_page + 1} из {total_pages}:", ""]
        for index, view in enumerate(views, start=start + 1):
            marker = "активный" if view.is_active else "не активный"
            lines.append(
                f"{index}. {view.title} — {view.role_title}, {marker}, "
                f"сообщений: {view.message_count}"
            )
        lines.append("")
        lines.append("Нажмите название, чтобы открыть диалог, или «Удалить» рядом с ним.")
        return ScreenResponse(
            text=prefix + "\n".join(lines),
            screen=Screen.DIALOGS,
            dialogs=views,
            page=current_page,
            total_pages=total_pages,
        )
