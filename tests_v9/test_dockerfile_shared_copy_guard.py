"""حارس نشر: كلّ خدمة تستورد حزمة ``shared`` يجب أن تنسخها صورتها.

عطل إنتاجيّ حقيقيّ (ai-agronomist بعد V58+): أضاف الكود ``from shared.ai import
tool_schema`` لكنّ ``services/ai_agronomist/Dockerfile`` لم ينسخ ``shared/`` ⇒
تحطّم الحاوية عند الإقلاع بـ``ModuleNotFoundError: No module named 'shared'``.
لم تمسكه بوّابة CI لأنّها تشغّل الاختبارات من جذر المستودع حيث ``shared`` متاح.

هذا الحارس ساكن (مسح نصّيّ، بلا خدمات/بناء) ويمنع تكرار الصنف: لأيّ خدمة يستورد
أيّ ملفّ ``.py`` فيها ``shared`` (كحزمة أعلى)، يجب أن يحوي ``Dockerfile`` سطر
``COPY shared`` (نمط guardrails-engine). منطق صرف — وظيفة Unit Tests.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_SERVICES = _ROOT / "services"

# استيراد حزمة ``shared`` الجذريّة: ``import shared`` أو ``from shared[.x] import``.
_IMPORTS_SHARED = re.compile(r"^\s*(?:from|import)\s+shared(?:\.|\s|$)", re.MULTILINE)
# نسخ الحزمة إلى الصورة: ``COPY shared ...`` أو ``COPY shared/ ...``.
_COPIES_SHARED = re.compile(r"^\s*COPY\s+shared\b", re.MULTILINE)


def _service_dirs_with_dockerfile() -> list[Path]:
    if not _SERVICES.is_dir():
        return []
    return sorted(d for d in _SERVICES.iterdir() if d.is_dir() and (d / "Dockerfile").is_file())


def _service_imports_shared(svc: Path) -> str | None:
    """أوّل ملفّ ``.py`` في الخدمة يستورد ``shared`` (أو None)."""
    for py in svc.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        try:
            text = py.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if _IMPORTS_SHARED.search(text):
            return str(py.relative_to(_ROOT))
    return None


def test_services_importing_shared_copy_it_into_image():
    offenders: list[str] = []
    checked = 0
    for svc in _service_dirs_with_dockerfile():
        src = _service_imports_shared(svc)
        if src is None:
            continue
        checked += 1
        dockerfile = (svc / "Dockerfile").read_text(encoding="utf-8")
        if not _COPIES_SHARED.search(dockerfile):
            offenders.append(f"{svc.name}: يستورد shared ({src}) لكنّ Dockerfile بلا 'COPY shared'")
    assert checked > 0, "لم يُفحَص أيّ خدمة — تحقّق من مسار services/"
    assert not offenders, "خدمات تستورد shared دون نسخها في الصورة:\n  " + "\n  ".join(offenders)


def test_ai_agronomist_dockerfile_copies_shared_regression():
    """حارس انحدار مباشر للعطل المُصلَح (V58+ / ai-agronomist)."""
    dockerfile = (_SERVICES / "ai_agronomist" / "Dockerfile").read_text(encoding="utf-8")
    assert _COPIES_SHARED.search(dockerfile), (
        "ai_agronomist/Dockerfile يجب أن ينسخ shared/ (يستورد from shared.ai import tool_schema)"
    )
