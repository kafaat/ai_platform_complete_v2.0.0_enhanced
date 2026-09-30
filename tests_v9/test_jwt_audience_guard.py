"""CI-enforced guard: JWT audience contract across services.

السبب: test_jwt_audience_consistency في test_roadmap_phase23.py بلا marker
(يُستبعَد في CI) ويُرجع قائمة تقرير لا assert، فلا يُفشل CI عند الانتكاس. هذا
الملفّ يحرس العقد فعليّاً بـassert ومُعلَّم unit ليُشغَّل في وظيفة الوحدات.

العقد: كلّ المُصدِرين يُصدرون aud="sahool"، وكلّ فاكّي JWT يتحقّقون من
audience="sahool" (وإلّا رفض PyJWT توكنات auth الصالحة — كسر مصادقة الخدمات).
"""

from __future__ import annotations

import glob
import os
import re

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _decoders_without_audience() -> list[str]:
    offenders: list[str] = []
    for py in glob.glob(os.path.join(ROOT, "services/**/*.py"), recursive=True):
        if "__pycache__" in py:
            continue
        txt = open(py, encoding="utf-8", errors="ignore").read()
        # \w* يلتقط الأسماء المستعارة مثل _jwt.decode / jose_jwt.decode
        for m in re.finditer(r"\w*jwt\.decode\(", txt):
            window = txt[m.start() : m.start() + 250]
            depth, end = 0, len(window)
            for i, ch in enumerate(window):
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            if "audience" not in window[:end]:
                offenders.append(os.path.relpath(py, ROOT))
    return offenders


@pytest.mark.unit
def test_all_jwt_decoders_validate_audience():
    offenders = _decoders_without_audience()
    assert not offenders, f"فاكّو JWT بلا audience (تسرّب اتّساق): {sorted(set(offenders))}"


@pytest.mark.unit
def test_issuers_emit_aud_sahool():
    auth = open(os.path.join(ROOT, "services/auth/main.py"), encoding="utf-8").read()
    plat = open(os.path.join(ROOT, "services/sahool-platform/api/main.py"), encoding="utf-8").read()
    # regex مرن (يقبل '/" ومسافات) — لا يكسره إعادة تنسيق
    aud_re = re.compile(r"""['"]aud['"]\s*:\s*['"]sahool['"]""")
    assert aud_re.search(auth), "auth لا يُصدر aud=sahool"
    assert aud_re.search(plat), "sahool-platform لا يُصدر aud=sahool"


@pytest.mark.unit
def test_supervisor_validates_audience():
    # JWT-DECODE-OUTSIDE-SHARED-SECURITY-01: المشرفُ يفكّ الآن بالوحدة المشتركة، فالجمهورُ
    # يُفرَض هناك مرّةً واحدة. الانتكاسةُ التي يحرسها هذا الاختبار (فكٌّ بلا جمهور) تعود إمّا
    # بفكٍّ محلّيّ بلا audience (يلتقطه test_all_jwt_decoders_validate_audience) أو بوحدةٍ
    # مشتركة لا تفرضه — فيُقاس الطرفان.
    sup = open(os.path.join(ROOT, "services/supervisor-agent/main.py"), encoding="utf-8").read()
    shared = open(os.path.join(ROOT, "shared/security/access_tokens.py"), encoding="utf-8").read()
    local = re.search(r"""audience\s*=\s*['"]sahool['"]""", sup)
    delegated = "decode_access_token(" in sup and re.search(
        r"""ACCESS_TOKEN_AUDIENCE\s*=\s*['"]sahool['"]""", shared
    )
    assert local or delegated, "supervisor لا يتحقّق من aud=sahool (انتكاسة)"
    if delegated:
        assert shared.count("audience=ACCESS_TOKEN_AUDIENCE") == 2, (
            "الوحدة المشتركة لا تمرّر الجمهور لكلتا الخلفيّتين"
        )
