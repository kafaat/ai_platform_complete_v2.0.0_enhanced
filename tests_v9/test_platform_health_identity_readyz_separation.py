"""فصلُ الهويّة الثابتة عن الوضع المتحوّل في `platform_health.py`.

**نُقِل من** `tests_v9/test_s5_decision_live_closure_receipt.py` عند تقاعد ذلك
الملفّ — الاختبارُ يخصّ `platform_health.py` لا مُجمِّع S5، وكان يعيش في ملفٍّ
غيرِ موضعه. لا علاقةَ له بأيّ مُنتِج S5؛ هذا نقلٌ بلا تغييرِ سلوك.

**الخاصّيّةُ المحروسة:** `runtime_evidence_identity` (الهويّةُ الثابتة —
`git_sha`/`build_id` من ملفّ صورةٍ غيرِ قابلٍ للتعديل) يجب ألّا تستدعي
`get_platform_decision_sor_mode` — قراءةُ وضعٍ متحوّل. ولو استدعتْه لصارت
الهويّةُ الثابتةُ تعتمد على حالةٍ تتغيّر زمنَ التشغيل، فتفقد ثباتَها. والوضعُ
المتحوّل مكانُه الصحيح `readyz` وحدَه.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def test_platform_readyz_exposes_mutable_mode_without_polluting_immutable_identity():
    src = (ROOT / "services/sahool-platform/api/routers/platform_health.py").read_text(
        encoding="utf-8"
    )
    identity_body = src[
        src.index("def runtime_evidence_identity") : src.index('@router.get("/healthz")')
    ]
    ready_body = src[src.index("async def readyz") :]
    assert "get_platform_decision_sor_mode" not in identity_body
    assert "get_platform_decision_sor_mode" in ready_body
    assert 'body["decision_sor"]' in ready_body
