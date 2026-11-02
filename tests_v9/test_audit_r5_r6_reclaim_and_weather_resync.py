"""شواهد انحدار R5/R6 (تدقيق المصدر 2026-11-01) — بلا خدمات حيّة، والحدودُ دوالٌّ مُرقَّعة.

R5: نيّةُ إبطال كاش الراستر العالقة في ``running`` (عاملٌ مات بين المطالبة والإنهاء)
    لم تكن تُطالَب ثانيةً أبداً. الاستعادةُ نفسُها SQL فتُقاس على Postgres حيّ في
    ``test_d1_raster_invalidation_owner_api_integration.py``؛ وهنا الشطرُ البايثونيّ:
    الاستعادةُ تَعُدّ المحاولةَ الضائعة، والمستنفَدةُ تنتهي ``failed`` بلا إرسال.
R6: مجموعةُ مواقع الطقس كانت تُبنى مرّةً عند الإقلاع (``load_from_db``)، فالحقلُ
    المُنشَأ بعده لا يُسحَب طقسُه حتّى إعادة التشغيل، والمحذوفُ يبقى يُسحَب.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services/sahool-platform"
pytestmark = pytest.mark.unit

if str(PLATFORM) not in sys.path:
    sys.path.insert(0, str(PLATFORM))


# ── R5: حدُّ المحاولات بعد الاستعادة ─────────────────────────────────────────


def _reclaimed_job(attempts: int) -> dict:
    return {
        "id": 7,
        "tenant_id": "00000000-0000-0000-0000-000000000001",
        "field_id": "f1",
        "parameters": '{"request_id": "field.geometry.updated:f1:rev1", "reason": "r"}',
        "result": (
            '{"lease": {"token": "tok", "expires_at": "2026-11-02"}, '
            f'"reclaimed": true, "attempts": {attempts}}}'
        ),
    }


async def test_reclaimed_intent_that_exhausted_its_attempts_fails_without_sending(monkeypatch):
    from api import spatial_sync

    finish = AsyncMock(return_value="failed")
    monkeypatch.setattr(spatial_sync, "_finish", finish)
    send = AsyncMock()

    outcome = await spatial_sync.deliver(None, _reclaimed_job(spatial_sync.MAX_ATTEMPTS), send=send)

    assert outcome == "failed"
    send.assert_not_awaited()
    kwargs = finish.await_args.kwargs
    assert kwargs["status"] == "failed"
    assert kwargs["attempts"] == spatial_sync.MAX_ATTEMPTS
    assert "lease expired" in kwargs["error"]
    assert finish.await_args.args[2] == "tok", "الإنهاءُ CAS على رمز الإجارة الجديدة"


async def test_reclaimed_intent_with_attempts_left_is_redelivered_with_the_same_key(monkeypatch):
    from api import spatial_sync

    finish = AsyncMock(return_value="delivered")
    monkeypatch.setattr(spatial_sync, "_finish", finish)
    send = AsyncMock(return_value={"accepted": True, "deduplicated": True})

    outcome = await spatial_sync.deliver(None, _reclaimed_job(1), send=send)

    assert outcome == "delivered"
    assert send.await_args.kwargs["request_id"] == "field.geometry.updated:f1:rev1"
    assert finish.await_args.kwargs == {
        "status": "completed",
        "attempts": 2,
        "ack": {"accepted": True, "deduplicated": True},
    }


def test_claim_statement_reclaims_running_rows_and_counts_the_lost_attempt():
    """الحارسُ البنيويّ للعبارة؛ دلالتُها تُقاس حيّةً في اختبار التكامل."""
    import inspect

    from api import spatial_sync

    src = inspect.getsource(spatial_sync.claim_due)
    assert "status = 'running'" in src, "R5: running منتهي الإجارة لا يُطالَب ⇒ عالقٌ للأبد"
    assert "'reclaimed', j.status = 'running'" in src
    assert "THEN 1 ELSE 0 END" in src, "الاستعادةُ بلا عَدٍّ للمحاولة ⇒ لا حدَّ لها"
