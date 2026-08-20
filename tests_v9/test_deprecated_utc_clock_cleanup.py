"""`DEPRECATED-UTC-CLOCK-01` — وما كشفه التنظيف من عطلٍ ليس إهمالاً.

`datetime.utcnow()` مُهمَلة منذ Python 3.12 لأنّها تُرجِع لحظةً **بلا منطقة**: نصٌّ
يقول UTC ونوعٌ لا يقوله، فأيّ مقارنةٍ مع لحظةٍ واعية ترفع `TypeError` وأيّ تخزينٍ
في `timestamptz` يُفسَّر بتوقيت الخادم.

لكنّ التحويل **ليس مسحاً ميكانيكيّاً**، وهذا هو مضمون هذا الملفّ: ثلاثة مواضع
كانت آمنة بالقياس، وموضعٌ رابع كان عطلاً حقيقيّاً مختبئاً تحت لافتة الإهمال،
وعنقودٌ خامس بقي **دَيناً مُعلَناً** لأنّ تحويله يغيّر عقداً قائماً.

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

import ast
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]

# العنقود المُعلَن دَيناً: `core/offline_first.py` يُنتِج `created_at` naive،
# و`api/sync_delta.py:26-28` يُصرّح أنّ مقارنة الـcursor **معجميّة** ومبنيّة على
# هذا الشكل بعينه. تحويلُ المُنتِج وحده يُدخِل لاحقة `+00:00` فيخلق حدَّ ترتيبٍ
# مختلطاً بين قيمٍ قديمة وجديدة عند اللحظة نفسها. إغلاقه يحتاج حسم دلالة الـcursor
# لا إعادة تسمية دالّة — فهو شريحةٌ بذاتها، لا ذيلٌ لهذه.
DECLARED_DEBT = {
    "services/sahool-platform/core/offline_first.py",
    "services/sahool-platform/tests/test_offline_first.py",
}


def _sources() -> list[Path]:
    skip = {".git", "node_modules", "__pycache__", ".venv", "venv", "build", "dist"}
    return [p for p in ROOT.rglob("*.py") if not any(part in skip for part in p.parts)]


def _calls_utcnow(path: Path) -> bool:
    """استدعاءٌ **مُنفَّذ** لا ذِكرٌ في تعليقٍ أو نصّ.

    الفحص بـ`ast` لا بـ`grep`: ثلاثة تعليقات في هذه الشجرة تشرح العطل بذكر اسمه،
    وإدانتُها إيجابيّةٌ كاذبة تُدرِّب كاتبها على حذف التوثيق.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "utcnow"
        ):
            return True
    return False


def test_no_source_outside_the_declared_debt_calls_the_deprecated_clock():
    offenders = sorted(
        str(p.relative_to(ROOT))
        for p in _sources()
        if _calls_utcnow(p) and str(p.relative_to(ROOT)) not in DECLARED_DEBT
    )
    assert not offenders, (
        f"`datetime.utcnow()` مُنفَّذة خارج الدَّين المُعلَن: {offenders}. "
        "حوِّلها إلى `datetime.now(UTC)` بعد قياس أثرها على الشكل المُسلسَل — "
        "أو أعلِنها في `DECLARED_DEBT` بسببٍ مكتوب، ولا تُوسّع القائمة بلا سبب"
    )


def test_the_declared_debt_is_real_and_shrinks_only():
    """دَينٌ يُعلَن عن ملفٍّ نظيف يصير إعفاءً دائماً بلا صاحب."""
    stale = sorted(rel for rel in DECLARED_DEBT if not _calls_utcnow(ROOT / rel))
    assert not stale, f"مدخلٌ في الدَّين بلا استدعاءٍ فعليّ — يُحذَف لا يُترَك: {stale}"


def test_the_lexical_cursor_contract_that_keeps_the_debt_open_still_says_so():
    """الدَّينُ مشروطٌ بعقدٍ قائم؛ فإن زال العقد زال سببُ التأجيل.

    وهذا هو ما يمنع الدَّين من أن يصير أبديّاً: إن حُسِمت دلالةُ الـcursor يوماً،
    يحمرّ هذا الاختبار فيُعاد النظر في التأجيل بدل أن يُنسى.
    """
    delta = (ROOT / "services/sahool-platform/api/sync_delta.py").read_text(encoding="utf-8")
    assert "نصّيّة معجميّة" in delta, (
        "زال العقد المعجميّ الذي يُبرِّر تأجيل عنقود offline_first — أعِد تقييم الدَّين"
    )


# ── العطل الذي لم يكن إهمالاً ────────────────────────────────────────────────


def test_a_guardrail_event_carries_the_moment_it_happened_not_the_import_time():
    """`= datetime.utcnow().isoformat()` قيمةٌ افتراضيّة تُقيَّم **مرّةً** عند الاستيراد.

    فكلّ أحداث الحارس في عمليّةٍ واحدة كانت تُنشَر بختمِ لحظةِ الإقلاع نفسه. مقيسٌ
    بالتشغيل قبل الإصلاح: حدثان أُنشئا بفارق 1.1 ثانية حملا الطابع ذاته حرفيّاً.

    وهو أخطر من غياب الطابع: حقلٌ اسمه `timestamp` في مسارٍ تدقيقيّ يُقرأ لحظةَ
    وقوعٍ، فيصير ترتيبُ الأحداث كلّه غير قابلٍ للاستخراج بلا أن يُحمِرّ شيء.
    """
    import sys

    sys.path.insert(0, str(ROOT / "services" / "ai_agronomist"))
    from guardrail_events import GuardrailEvent

    first = GuardrailEvent("t", "f", "block", "r", 0.9)
    time.sleep(0.01)
    second = GuardrailEvent("t", "f", "block", "r", 0.9)
    assert first.timestamp != second.timestamp, (
        "حدثان متتاليان يحملان الطابع نفسه — القيمة الافتراضيّة تُقيَّم عند الاستيراد"
    )
    parsed = datetime.fromisoformat(second.timestamp)
    assert parsed.tzinfo is not None, "طابعٌ بلا منطقة يُفسَّر بتوقيت الخادم عند التخزين"
    assert abs((datetime.now(UTC) - parsed).total_seconds()) < 60


# ── والتحويل الذي كان سيُغيّر الشكل السلكيّ بصمت ─────────────────────────────


def test_the_memory_models_keep_their_serialized_shape_after_dropping_json_encoders():
    """`json_encoders` مُهمَلة — وإسقاطُها **ليس** محايداً.

    التسلسل المدمج في Pydantic v2 يُخرِج لاحقة `Z`، و`.isoformat()` تُخرِج
    `+00:00`. و`farm_memory.py` يُدِيم هذه النماذج بـ`model_dump(mode="json")`،
    فالإزالة الساذجة كانت ستُعيد كتابة شكل كلّ مخزنٍ على القرص وتترك ملفّاتٍ
    مختلطة الشكل. `PlainSerializer` قِيس مطابقاً بايتاً، وهذا الاختبار يُثبِّته.
    """
    import sys

    sys.path.insert(0, str(ROOT))
    from shared.memory.models import ConversationTurn

    moment = datetime(2026, 8, 19, 21, 0, 0, tzinfo=UTC)
    turn = ConversationTurn(farm_id="f", user_query="q", ai_response="a", timestamp=moment)
    assert turn.model_dump(mode="json")["timestamp"] == "2026-08-19T21:00:00+00:00", (
        "تغيّر شكل الإدامة — الملفّات القائمة تصير مختلطة الشكل بلا إعلان"
    )
    assert isinstance(turn.model_dump(mode="python")["timestamp"], datetime), (
        '`when_used="json"` هي ما يُبقي الوضع البرمجيّ datetime لا نصّاً'
    )
    src = (ROOT / "shared/memory/models.py").read_text(encoding="utf-8")
    assert '"json_encoders"' not in src.replace("# `json_encoders`", ""), (
        "المفتاح المُهمَل عاد — والتحذير يُطلَق عند إنشاء كلّ صنف"
    )


def test_a_tokens_lifetime_equals_its_declared_window_exactly():
    """رفعه Copilot على #877 وأصاب: نداءان للساعة يُنتِجان صلاحيّةً لا تطابق عقدها.

    ``jose`` يحوّل الطابع عبر ``utctimetuple()``، أي يقصّ إلى ثوانٍ كاملة. فنداءان
    منفصلان يتخطّيان حدّ الثانية يُعطيان ``exp - iat`` أقصر بثانية من المدّة
    المُعلَنة. سباقٌ نادر، لكنّ أثره صلاحيّةٌ تُخالف عقدها — ولا يُمسَك بتشغيلٍ
    واحد لأنّ النافذة ميكروثانية.

    فالمقيس هنا **بنيويّ لا زمنيّ**: هل تُقرأ الساعة مرّةً واحدة داخل الدالّة؟
    اختبارٌ يستدعيها ويقارن الفرق كان سيخضرّ في ٩٩٫٩٩٪ من التشغيلات وهو بعينه
    «أخضرُ عن سؤالٍ لم يُطرَح» الذي يرفضه هذا الملفّ.

    والعيب سابقٌ للتحويل من الساعة المُهمَلة (كان النداءان ``utcnow()``): لم
    يُدخِله التحويل، ولم يكن ليُصلحه — لولا مراجعةٌ خارجيّة نظرت إلى ما لم أنظر إليه.
    """
    source = (ROOT / "services/sahool-platform/api/main.py").read_text(encoding="utf-8")
    start = source.index("def create_token(")
    body = source[start : source.index("\n\n\n", start)]
    executed = [
        line for line in body.splitlines() if line.strip() and not line.strip().startswith("#")
    ]
    reads = sum(line.count("datetime.now(") for line in executed)
    assert reads == 1, (
        f"الساعة تُقرأ {reads} مرّة داخل `create_token` — الحقلان يجب أن يُشتقّا من "
        "لحظةٍ واحدة، وإلّا صارت الصلاحيّة أقصر بثانية عند تخطّي حدّ الثانية"
    )
