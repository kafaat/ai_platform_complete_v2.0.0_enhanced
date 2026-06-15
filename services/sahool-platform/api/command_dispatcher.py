"""api/command_dispatcher.py — مُوجِّه الأوامر (Command Handler Registry + dispatch).

البند P1 من مراجعة CQRS: فوق `CommandStore` القائم (v10، idempotency جاهز عبر
ON CONFLICT). يربط نوع الأمر بمعالِجه ويلفّ التنفيذ بدورة حياة الأمر:

  register(command_type, handler) ──┐
                                    ▼
  dispatch(registry, store, cmd):
    1. idempotency: أمر مُنفَّذ سابقاً (succeeded) → was_duplicate + النتيجة المخزّنة
       (لا إعادة تنفيذ — مزامنة mobile بعد offline تُعيد إرسال آمن).
    2. save (ON CONFLICT DO NOTHING) — الثابت القاعديّ.
    3. mark_processing → handler → mark_succeeded(result) / mark_failed(error).

⚠ هذا **الأساس** (تسجيل + توجيه) لا إعادة هيكلة الكتابة كاملةً. الخطوة التالية
(مؤجَّلة، غير كاسرة): FieldAggregate يلفّ الحقل+الموسم+النشاط، وتوجيه الـendpoints
تدريجيّاً عبر dispatch بدل الـINSERT المباشر (POST_DEPLOYMENT_ROADMAP — المرحلة ٣).

⚠ نقيّ وقابل للاختبار: dispatch يقبل أيّ store بعقد (get/save/mark_*) — يُختبَر
بمتجر ذاكرة وهميّ بلا قاعدة. المعالِجات async (تنفّذ كتابة الحالة + إصدار الأحداث).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger("sahool.command_dispatcher")

# معالِج أمر: async (command) -> dict نتيجة.
CommandHandler = Callable[[Any], Awaitable[dict]]


class CommandRegistry:
    """سجلّ معالِجات الأوامر: نوع واحد → معالِج واحد (مصدر حقيقة للتوجيه)."""

    def __init__(self) -> None:
        self._handlers: dict[str, CommandHandler] = {}

    def register(self, command_type: str, handler: CommandHandler) -> None:
        """يسجّل معالِجاً لنوع أمر. تكرار التسجيل خطأ (يمنع توجيهاً غامضاً)."""
        if command_type in self._handlers:
            raise ValueError(f"معالِج مُسجَّل مسبقاً لنوع الأمر '{command_type}'")
        self._handlers[command_type] = handler

    def handler_for(self, command_type: str) -> CommandHandler | None:
        return self._handlers.get(command_type)

    def registered_types(self) -> list[str]:
        return sorted(self._handlers)


async def dispatch(registry: CommandRegistry, store: Any, command: Any) -> Any:
    """ينفّذ أمراً عبر معالِجه مع idempotency + دورة حياة عبر CommandStore.

    store: كائن بعقد get/save/mark_processing/mark_succeeded/mark_failed (CommandStore
    أو وهميّ). command: كائن فيه command_id/command_type/... (Command).
    """
    from api.command_store import CommandStatus, DispatchResult

    # 1. idempotency: أمر منفَّذ سابقاً (succeeded) → النتيجة المخزّنة بلا إعادة تنفيذ؛
    #    أو قيد التنفيذ (processing — نسخة متزامنة/إعادة تشغيل أثناء الطلب) → لا نعيد
    #    تنفيذه (يكسر exactly-once). فقط failed/pending يسقطان للأسفل لإعادة المحاولة.
    existing = await store.get(command.command_id)
    if existing is not None:
        if existing.status == CommandStatus.SUCCEEDED:
            return DispatchResult(
                command_id=command.command_id,
                status=CommandStatus.SUCCEEDED,
                result=existing.result,
                was_duplicate=True,
            )
        if existing.status == CommandStatus.PROCESSING:
            return DispatchResult(
                command_id=command.command_id,
                status=CommandStatus.PROCESSING,
                was_duplicate=True,
            )

    # توجيه: لا معالِج ⇒ فشل صريح (لا تنفيذ أعمى).
    handler = registry.handler_for(command.command_type)
    if handler is None:
        return DispatchResult(
            command_id=command.command_id,
            status=CommandStatus.FAILED,
            error=f"لا معالِج مُسجَّل لنوع الأمر '{command.command_type}'",
        )

    # 2. حفظ (ON CONFLICT DO NOTHING) ثمّ 3. تنفيذ ضمن دورة الحياة.
    await store.save(command)
    await store.mark_processing(command.command_id)
    try:
        result = await handler(command)
        result = result if isinstance(result, dict) else {}
        await store.mark_succeeded(command.command_id, result)
        return DispatchResult(
            command_id=command.command_id, status=CommandStatus.SUCCEEDED, result=result
        )
    except Exception as e:  # noqa: BLE001 — أيّ فشل معالِج يُسجَّل ويُرجَع (لا يُسقِط)
        logger.warning("فشل معالِج الأمر %s: %s", command.command_type, e)
        await store.mark_failed(command.command_id, str(e))
        return DispatchResult(
            command_id=command.command_id, status=CommandStatus.FAILED, error=str(e)
        )
