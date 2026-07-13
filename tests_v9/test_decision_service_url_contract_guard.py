"""حارس ساكن: عنوان decision-service الافتراضيّ في الخدمات يطابق خدمة compose الفعليّة.

خلفيّة (تدقيق البوّابة/العملاء — P0): كان vegetation_runtime.py يُعيّن الافتراض
``http://decision-service:8007`` بينما خدمة compose هي ``sahool-decision-service:8160``،
ولا تُمرَّر ``DECISION_SERVICE_URL`` إلى خدمة النبات في docker-compose.v9.yml — فيفشل
دفع لقطات النبات إلى decision-service صامتاً عند غياب env.

الحارس يمنع انحدار الاسم/المنفذ الوهميّ ويؤكّد تمرير env في compose.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = "http://sahool-decision-service:8160"
PHANTOM = "decision-service:8007"


def test_vegetation_runtime_default_points_at_real_compose_service() -> None:
    src = (ROOT / "services/vegetation-analysis-service/vegetation_runtime.py").read_text(
        encoding="utf-8"
    )
    # الافتراض الصحيح موجود، والوهميّ غائب.
    assert CANONICAL in src, (
        "vegetation DECISION_SERVICE_URL default must be the real compose service"
    )
    assert PHANTOM not in src, f"phantom decision-service address {PHANTOM!r} must not remain"


def test_compose_passes_decision_service_url_to_vegetation() -> None:
    compose = (ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8")
    # نحصر الفحص على كتلة خدمة النبات.
    m = re.search(r"^  sahool-vegetation-analysis:\n(?:.*\n)*?(?=^  \S)", compose, re.MULTILINE)
    assert m, "sahool-vegetation-analysis service block not found"
    block = m.group(0)
    assert "DECISION_SERVICE_URL" in block, "vegetation service must set DECISION_SERVICE_URL"
    assert "sahool-decision-service:8160" in block


def test_no_service_defaults_to_phantom_decision_service() -> None:
    # لا يُبقي أيّ ملفّ خدمة على الافتراض الوهميّ (اسم/منفذ لا يوجدان في compose).
    offenders = []
    for path in (ROOT / "services").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        try:
            if PHANTOM in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(ROOT)))
        except (UnicodeDecodeError, OSError):
            continue
    assert not offenders, f"phantom decision-service address in: {offenders}"
