"""حارس التوكن الخدميّ (_require_service_token) — fail-closed + مقارنة زمن ثابت.

النقاط الداخليّة (/internal/...) محميّة بـSAHOOL_AGENT_TOKEN. هذه الاختبارات تثبّت:
السرّ الغائب يُرفض (fail-closed)، التوكن الخاطئ/الغائب يُرفض (403)، والصحيح يمرّ —
والمقارنة تمرّ عبر hmac.compare_digest (زمن ثابت) لا == (تسريب توقيت).
"""

from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit  # CI يشغّل -m unit؛ بلا الوسم لا يُنفَّذ

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")


@pytest.fixture(scope="module")
def m():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")
    # P1 decomposition: الحارس انتقل من api.main إلى api/service_token_auth.py (تستهلكه
    # نقاط /internal في api/routers/internal_service.py) — نفحصه في موضعه الجديد.
    import api.service_token_auth as guard_mod

    return guard_mod


def test_missing_secret_is_fail_closed(m, monkeypatch):
    """لا SAHOOL_AGENT_TOKEN في البيئة ⇒ تُرفض كلّ المحاولات (لا تُفتح النقطة)."""
    from fastapi import HTTPException

    monkeypatch.delenv("SAHOOL_AGENT_TOKEN", raising=False)
    with pytest.raises(HTTPException) as e:
        m._require_service_token(x_agent_token="anything")
    assert e.value.status_code == 403


def test_wrong_and_missing_token_rejected(m, monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "s3cret-agent-token")
    for bad in ("wrong", "", None):
        with pytest.raises(HTTPException) as e:
            m._require_service_token(x_agent_token=bad)
        assert e.value.status_code == 403


def test_correct_token_passes(m, monkeypatch):
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "s3cret-agent-token")
    # لا استثناء ⇒ مقبول (الدالّة تُعيد None ضمنيّاً)
    assert m._require_service_token(x_agent_token="s3cret-agent-token") is None


def test_uses_constant_time_compare(m):
    """تأكيد بنيويّ: الحارس يستخدم hmac.compare_digest لا == (منع تسريب التوقيت)."""
    import inspect

    src = inspect.getsource(m._require_service_token)
    assert "compare_digest" in src, "يجب أن تكون المقارنة بزمن ثابت (hmac.compare_digest)"


# ─── توسعةُ النطاق: من دالّةٍ واحدةٍ مُثبَّتةٍ إلى الصنف كلِّه ─────────────────
#
# **العطلُ الذي وُجِدت هذه لأجله:** الاختبارُ أعلاه كان يفحص **دالّةً واحدة** بالاسم
# (`api/service_token_auth.py`)، فبقي أخضرَ بينما **ثمانيةٌ** من عشرين موضعَ مصادقةٍ
# في الشجرة تقارن بـ`!=` — قناةُ توقيتٍ جانبيّةٌ على سرٍّ خدميّ. أمسكها تدقيقُ المالك
# (20260920T182017Z, F-GLOBAL-09) من طرفها لا من أصلها: سمّى `soil-service` وحدَها.
#
# والدرسُ أنّ حارساً يُثبّت **مثيلاً** لا يحرس **صنفاً**: تسعةُ مواضعَ طبّقت القاعدة
# صحيحةً (إحداها تكتب صراحةً «L5 FIX: مقارنة بزمن ثابت … لإغلاق قناة توقيت جانبيّة»)
# وثمانيةٌ لم تطبّقها، في شجرةٍ واحدة — بل في `scout-ingest-service` نفسِها كان
# اثنان يستعملان `service_token_ok` والثالث `!=`. فالمعرفةُ كانت حاضرةً والحارسُ
# ضيّقاً، وهو صنفُ «توسعة C1» نفسُه (pip-audit: أربعةُ ملفّات فأفلتت خدماتٌ كاملة).
#
# ولذلك يمسح هذا الشاهدُ الشجرةَ **بالسلوك لا بالاسم**: أيُّ مقارنةِ مساواةٍ طرفُها
# اسمٌ توكنيّ تفشل، مهما سُمّيت الدالّةُ الحاضنة.

_TOKEN_NAME = re.compile(r"(?:AGENT|SERVICE|READ|WEBHOOK|SECRET|API)_(?:TOKEN|SECRET|KEY)$", re.I)
_SCAN_ROOTS = ("services", "shared", "agents", "bots")
_SKIP_PARTS = {"__pycache__", "node_modules", ".git", "backups", "migrations"}


def _is_token_ref(node: ast.AST) -> bool:
    """هل يشير العقدةُ إلى سرٍّ خدميّ بالاسم؟ (`AGENT_TOKEN` · `settings.READ_TOKEN` …)"""
    if isinstance(node, ast.Name):
        return bool(_TOKEN_NAME.search(node.id))
    if isinstance(node, ast.Attribute):
        return bool(_TOKEN_NAME.search(node.attr))
    return False


def _equality_comparisons_on_secrets(path: Path) -> list[tuple[int, str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - ملفّ غير قابل للتحليل
        return []
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        if not any(isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops):
            continue
        operands = [node.left, *node.comparators]
        if any(_is_token_ref(o) for o in operands):
            hits.append((node.lineno, ast.dump(node)[:80]))
    return hits


def _source_files() -> list[Path]:
    root = Path(ROOT).resolve()
    out: list[Path] = []
    for top in _SCAN_ROOTS:
        base = root / top
        if not base.is_dir():
            continue
        for p in base.rglob("*.py"):
            if _SKIP_PARTS & set(p.parts):
                continue
            if p.name.startswith("test_") or "tests" in p.parts:
                continue
            out.append(p)
    return out


def test_no_service_secret_is_compared_with_equality_anywhere():
    """راتشِتٌ على **الصنف**: لا مقارنةَ مساواةٍ على سرٍّ خدميّ في أيّ مصدرٍ مُنتِج.

    المقارنةُ الصحيحة ``hmac.compare_digest`` أو ``shared.security.trusted_tenant
    .service_token_ok`` (وهو غلافُها الفاشل-مغلقاً على سرٍّ فارغ).

    **يفشل هذا الشاهدُ إن أُعيد أيُّ `!=`** — وهو الاتّجاه المقصود: الحارسُ الضيّق
    كان يمرّ بثمانيةِ انتهاكات، وهذا لا يمرّ بواحد.
    """
    root = Path(ROOT).resolve()
    violations: list[str] = []
    for path in _source_files():
        for lineno, _dump in _equality_comparisons_on_secrets(path):
            violations.append(f"{path.relative_to(root)}:{lineno}")
    assert not violations, (
        "مقارنةُ مساواةٍ على سرٍّ خدميّ (قناةُ توقيتٍ جانبيّة) — استعمل "
        "`service_token_ok` أو `hmac.compare_digest`:\n  " + "\n  ".join(sorted(violations))
    )


def test_the_scanner_would_see_a_reintroduced_equality_check(tmp_path):
    """تكذيبُ الشاهد: لو عاد `!=` لَوجب أن يُرى — وإلّا كان أخضرُه صمتاً لا قياساً.

    بلا هذا، أيُّ خطأٍ في `_is_token_ref` يجعل الماسحَ يمرّ بكلّ شيء ويبدو سليماً.
    """
    probe = tmp_path / "probe.py"
    probe.write_text("def guard(provided):\n    return provided != AGENT_TOKEN\n", encoding="utf-8")
    assert _equality_comparisons_on_secrets(probe), "الماسحُ أعمى عن `!=` على سرٍّ خدميّ"

    clean = tmp_path / "clean.py"
    clean.write_text(
        "def guard(provided):\n    return service_token_ok(provided, AGENT_TOKEN)\n",
        encoding="utf-8",
    )
    assert not _equality_comparisons_on_secrets(clean), "الماسحُ يُحمِّر المقارنةَ الصحيحة"


# ─── شاهدٌ سلوكيّ: التوحيدُ لم يُغيّر الدلالة ───────────────────────────────
#
# الماسحُ أعلاه بنيويّ — يقول «لا `!=`» ولا يقول «ما زال يرفض». وتمييزُ 503 (سرٌّ
# غيرُ مضبوط ⇒ عطلُ مشغّل) عن 401 (توكنٌ خاطئ ⇒ رفضُ مُستدعٍ) دلالةٌ مقصودةٌ كان
# يمكن أن تضيع في التحويل، لأنّ `service_token_ok` يجمع الحالتين في `False`.


def _load(rel: str, name: str):
    """يحمّل وحدةَ خدمةٍ بمسارها الخاصّ (كنمط بقيّة شواهد الخدمات هنا)."""
    import importlib.util

    path = Path(ROOT).resolve() / rel
    svc = str(path.parent)
    if svc not in sys.path:
        sys.path.insert(0, svc)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("rel", "name", "guard", "secret_attr", "env", "unset_code", "wrong_code"),
    [
        # الخدمةُ التي سمّاها التدقيق، ونقطةُ القراءة التي كانت الشاذّةَ بين شقيقتين
        # تستعملان `service_token_ok` في المجلّد نفسِه.
        (
            "services/soil-service/main.py",
            "soil_probe",
            "_require_service_token",
            "AGENT_TOKEN",
            "SAHOOL_AGENT_TOKEN",
            503,
            401,
        ),
        (
            "services/scout-ingest-service/main.py",
            "scout_probe",
            "_require_read_token",
            "READ_TOKEN",
            "SCOUT_INGEST_READ_TOKEN",
            503,
            401,
        ),
    ],
)
def test_the_rewrite_kept_the_operator_caller_distinction(
    rel, name, guard, secret_attr, env, unset_code, wrong_code, monkeypatch
):
    """سرٌّ غيرُ مضبوط ⇒ 503 · توكنٌ خاطئ/غائب ⇒ 401 · الصحيحُ يمرّ."""
    from fastapi import HTTPException

    pytest.importorskip("fastapi")
    module = _load(rel, name)
    fn = getattr(module, guard)

    # السرُّ يُقرأ عند الاستيراد في هاتين الخدمتين (نمطُ البيت المُعلَن: قلبُ سرٍّ
    # يوجب إعادةَ تشغيل الحاوية)، فنضبطه على الوحدة لا على البيئة.
    monkeypatch.setattr(module, secret_attr, "", raising=True)
    with pytest.raises(HTTPException) as e:
        fn("anything")
    assert e.value.status_code == unset_code, f"{env} غير مضبوط يجب أن يُرجِع {unset_code}"

    monkeypatch.setattr(module, secret_attr, "s3cret-agent-token", raising=True)
    for bad in ("wrong", "", None):
        with pytest.raises(HTTPException) as e:
            fn(bad)
        assert e.value.status_code == wrong_code, f"توكنٌ {bad!r} يجب أن يُرجِع {wrong_code}"

    assert fn("s3cret-agent-token") is None, "التوكنُ الصحيح يجب أن يمرّ"
