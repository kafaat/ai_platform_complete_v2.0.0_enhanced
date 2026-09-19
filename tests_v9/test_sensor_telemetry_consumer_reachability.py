"""`SENSOR-TELEMETRY-INGEST-REACHES-NO-AGRONOMIC-CONSUMER-01` — مبتلَعٌ ينجح ولا يصل.

**المقيس.** `POST /api/v1/devices/{device_id}/telemetry` يقبل قراءةَ `soil_moisture`،
يردّ **201** ورسالةَ «سُجّلت القراءة»، ويكتب في `device_telemetry`. وكلُّ مستهلكٍ زراعيٍّ
لرطوبة التربة يقرأ من `soil_observations` عبر `_latest_soil_moisture` — نقطةُ الحقل،
واكتمالُ الحقل، وتوأمُ المياه، ومكنسةُ النضارة. فالمسارُ **التلقائيّ** بين الجدولين
منقطع: لا عاملٌ ولا مجدوِلٌ ولا سيرُ عملٍ ينقل قراءةً من الأوّل إلى الثاني.

**وثمّة جسرٌ واحد، وهو ليس تلقائيّاً** (كشفته مراجعةُ المالك، وكانت دعواي الأولى
**مطلَقةً وكاذبة**): `scripts/soil/reconcile_historical.py::reconcile_device_telemetry`
يقرأ `device_telemetry` ويكتب `soil_observations` ويُدرِج مهمّةَ إسقاط. لكنّه أداةُ
مشغّلٍ تُستدعى باليد (`--tenant` + `DATABASE_URL`)، لا يستدعيها شيءٌ في الشجرة. وما
تُدرجه يحمل `'suspect'` وثقةً 0.60 و`depth_unknown`/`calibration_unknown` — وذلك
بحسب `SOIL-MOISTURE-UNIT-IDENTITY-01` شاهدٌ مرئيٌّ **لا يُهيّئ** توأمَ المياه.

فالنتيجةُ أنّ جهازاً يدفع رطوبةَ تربةٍ ينال **نجاحاً**، ولا تبلغ قراءتُه قراراً واحداً
ما لم يُشغّل مشغّلٌ بشريٌّ ردماً بأثرٍ رجعيّ — وحتّى حينئذٍ تصل شاهداً لا بذرة.
الصنفُ هو «النجاحُ الصامت» نفسُه الذي أُغلق أربعَ مرّاتٍ في هذا المستودع، ووجهُه هنا
أخبثُ: العطلُ في **الصمت** لا في الرفض — الرفضُ كان سيُعلِم الدافعَ فوراً.

**وما جعله غيرَ مرئيّ ستّةُ مواضعَ من النثر تقول العكس**، منها تعليقان داخل مكنسة
النضارة نفسِها. فمن يدقّق الشجرة يقرأ أنّ المسار موصول — وهو ليس كذلك.

**وما لا يفعله هذا الملفّ:** لا يوصّل الجدولين ولا يفرض توصيلَهما. التوصيلُ قرارُ
مسارِ بياناتٍ له عوائقُ `AI-RUNTIME-WIRING-01` الثلاثةُ نفسُها (تزامنٌ · لا اتّصال في
المايسترو · ترتيبُ اللقطة). فالمقيسُ هنا أنّ **الوصفَ يطابق السلوك**، وأنّ الانفصال
مربوطٌ بحالة الفجوة في الاتّجاهين — فمن يوصّل غداً يجد الشاهدَ يطالبه بإغلاق الفجوة،
لا يجده يعاقبه على الإصلاح.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services/sahool-platform"
FIELD_CONTEXT = PLATFORM / "api/field_context.py"
DEVICES_ROUTER = PLATFORM / "api/routers/devices.py"
REGISTRY = ROOT / "sahool-brain/gaps/registry.md"

GAP_ID = "SENSOR-TELEMETRY-INGEST-REACHES-NO-AGRONOMIC-CONSUMER-01"

#: قارئُ رطوبة التربة الذي يستهلكه كلُّ مسارٍ زراعيّ.
AGRONOMIC_READER = "_latest_soil_moisture"
#: نقطةُ الابتلاع التي يدفع إليها الجهاز.
INGEST_HANDLER = "ingest_telemetry"


def _function(path: Path, name: str) -> ast.AST:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"اختفت `{name}` من {path.name} — حدِّث الشاهدَ أو القسم")


def _sql_text(func: ast.AST) -> str:
    """نصوصُ SQL الحرفيّة داخل الدالّة، مضمومة.

    تُقرأ من شجرة النحو لا بقراءة الملفّ كلِّه، وإلّا خلط الشاهدُ استعلامَ دالّةٍ
    بجارتها فصار **أوسعَ من دعواه** — وهو ما يُنتج حمرةً كاذبة.
    """
    return "\n".join(
        node.value
        for node in ast.walk(func)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    )


def _sql_text_of_path(path: Path, name: str) -> str:
    """نصوصُ الدالّة **ومَن تستدعيه من جيرانها في الملفّ نفسِه** — لا الملفّ كلّه.

    RECONCILIATION-CURSOR-SKIPS-ROWS-THAT-BECOME-ELIGIBLE-01 فكّك
    `reconcile_device_telemetry` إلى مرورَين ودالّةِ أهليّةٍ واحدة
    (`_process_telemetry_row`) وثابتِ أعمدةٍ مشترك (`_TELEMETRY_COLUMNS`). فصار
    `_sql_text` على العقدة وحدَها يرى `soil_reconciliation_checkpoints` فقط، ويقول
    «لم يعد يقرأ `device_telemetry`» — **حمرةٌ كاذبة عن جسرٍ لم يتغيّر**، وهي وجهُ
    «قارئٍ أضيقَ من دعواه» بعد أن أغلق هذا الملفُّ وجهَه الآخر.

    والعلاجُ **ليس** قراءةَ الملفّ كلِّه: ذلك يُعيد الوسعَ الذي يحذّر منه `_sql_text`
    (استعلامُ ذراع `soil_readings` يدخل في حكمٍ عن ذراع `device_telemetry`). فتُتبَع
    **الأسماءُ التي تستعملها الدالّةُ فعلاً**، مأخوذةً من شجرة النحو: كلُّ اسمٍ يظهر
    داخلها ويُعرَّف في أعلى الملفّ (دالّةً أو ثابتاً) يدخل، وما عداه يبقى خارجاً.
    فالمدى يتبع المسارَ لا الملفّ.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    func = _function(path, name)
    used = {n.id for n in ast.walk(func) if isinstance(n, ast.Name)}
    collected = [func]
    for node in tree.body:
        if getattr(node, "name", None) in used and node is not func:
            collected.append(node)
        elif isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in used for t in node.targets
        ):
            collected.append(node)
    return "\n".join(_sql_text(node) for node in collected)


def _table_read_by_the_agronomic_reader() -> set[str]:
    sql = _sql_text(_function(FIELD_CONTEXT, AGRONOMIC_READER))
    return set(re.findall(r"\bFROM\s+(\w+)", sql, re.IGNORECASE))


def _table_written_by_the_ingest_endpoint() -> set[str]:
    sql = _sql_text(_function(DEVICES_ROUTER, INGEST_HANDLER))
    return set(re.findall(r"\bINSERT\s+INTO\s+(\w+)", sql, re.IGNORECASE))


def test_the_agronomic_reader_reads_the_canonical_store() -> None:
    """الحقيقةُ الأولى: القارئُ الزراعيُّ يقرأ `soil_observations` لا جدولَ الأجهزة."""
    tables = _table_read_by_the_agronomic_reader()
    assert "soil_observations" in tables, (
        f"`{AGRONOMIC_READER}` لم يعد يقرأ `soil_observations` (يقرأ {sorted(tables)}) — "
        "تغيّر مصدرُ الحقيقة الزراعيّة، فحدِّث القسمَ والنثرَ معه"
    )
    assert "device_telemetry" not in tables, (
        f"`{AGRONOMIC_READER}` صار يقرأ `device_telemetry` — الفجوةُ تغيّرت، حدِّث القسم"
    )


def test_the_ingest_endpoint_writes_the_device_table() -> None:
    """الحقيقةُ الثانية: نقطةُ الابتلاع تكتب `device_telemetry`."""
    tables = _table_written_by_the_ingest_endpoint()
    assert "device_telemetry" in tables, (
        f"`{INGEST_HANDLER}` لم يعد يكتب `device_telemetry` (يكتب {sorted(tables)}) — "
        "تغيّر مقصدُ الابتلاع، فحدِّث القسم"
    )


def _gap_status(gap_id: str) -> str:
    text = REGISTRY.read_text(encoding="utf-8")
    start = text.index(f"## {gap_id}")
    section = text[start : text.find("\n## ", start + 1)]
    match = re.search(r"\*\*الحالة:\*\*\s*([a-z]+)", section)
    assert match, f"{gap_id}: لا سطرَ حالة في قسمه"
    return match.group(1)


def test_the_separation_is_bound_to_the_registry_status_in_both_directions() -> None:
    """الانفصالُ مقيَّدٌ بالحالة — فالإصلاحُ يُطالِب بالإغلاق ولا يُعاقَب عليه.

    شاهدٌ يقول «الجدولان منفصلان» وحدَه يُجمّد العطل: من يوصّلهما غداً يجد اختباراً
    أحمرَ يمنعه. فالمقيسُ هو **الاتّفاق** بين الشجرة والسجلّ في الاتّجاهين — النمطُ
    نفسُه المستعمَل في `test_recommendation_runtime_reachability.py`.
    """
    read = _table_read_by_the_agronomic_reader()
    written = _table_written_by_the_ingest_endpoint()
    reachable = bool(read & written)
    status = _gap_status(GAP_ID)

    if reachable:
        assert status != "open", (
            f"صارت نقطةُ الابتلاع تكتب ما يقرؤه المستهلكُ الزراعيّ ({sorted(read & written)}) "
            "والقسمُ ما يزال `open` — اقلب الحالةَ بقياسها في الالتزام نفسِه"
        )
    else:
        assert status == "open", (
            "القسمُ يقول إنّ الفجوة أُغلقت، والجدولان ما زالا منفصلَين "
            f"(يُكتَب {sorted(written)} · يُقرَأ {sorted(read)}) — إغلاقٌ بلا مسار"
        )


BACKFILL = ROOT / "scripts/soil/reconcile_historical.py"
BACKFILL_FUNC = "reconcile_device_telemetry"


def test_the_one_bridge_is_named_and_is_an_operator_tool_not_a_pipeline() -> None:
    """الجسرُ يُسمّى ويُقاس — لأنّ إنكارَه هو ما أخطأتُ فيه أوّلاً.

    دعواي الأولى قالت «قارئا `device_telemetry` في الشجرة كلِّها اثنان»، وكانت
    **كاذبة**: بحثتُ في `services/` ووصفتُ النتيجةَ بأنّها الشجرةُ كلُّها — قارئٌ أضيقُ
    من دعواه، وهو الصنفُ الذي تُغلقه هذه الشريحة نفسُها. كشفته مراجعةُ المالك.

    فبدل تليين النصّ، يُقاس الجسرُ: موجودٌ، ويقرأ الجدولَ ويكتب المخزنَ القانونيّ،
    **ولا يستدعيه شيء**. فإن صار يوماً مُستدعًى من عاملٍ أو مجدوِل، احمرّ هذا الشاهد
    وطالب بإعادة قراءة الفجوة — وهو ما كانت الدعوى المطلَقة تعجز عنه.
    """
    assert BACKFILL.exists(), f"{BACKFILL.name}: اختفى الردمُ — أعِد قراءةَ الفجوة"
    sql = _sql_text_of_path(BACKFILL, BACKFILL_FUNC)

    # **تُقرأ الجُمَلُ لا النصّ.** أوّلُ صياغةٍ اكتفت بـ`"device_telemetry" in sql`،
    # فنجت طفرةُ تحويل `FROM` إلى جدولٍ آخر: الاسمُ باقٍ في اسم نقطة الحفظ وفي
    # `jsonb_build_object('legacy_table', …)` وفي مفتاح إزالة التكرار. قارئٌ أوسعُ من
    # دعواه ⇒ خُضرةٌ كاذبة — الصنفُ الذي تُغلقه هذه الشريحة، ظاهراً في شيفرتها.
    read = set(re.findall(r"\bFROM\s+(\w+)", sql, re.IGNORECASE))
    written = set(re.findall(r"\bINSERT\s+INTO\s+(\w+)", sql, re.IGNORECASE))
    assert "device_telemetry" in read, (
        f"`{BACKFILL_FUNC}` لم يعد يقرأ `device_telemetry` (يقرأ {sorted(read)}) — "
        "تغيّر الجسرُ الوحيد، فأعِد قراءةَ الفجوة وقسمَها"
    )
    assert "soil_observations" in written, (
        f"`{BACKFILL_FUNC}` لم يعد يكتب `soil_observations` (يكتب {sorted(written)}) — "
        "تغيّر الجسرُ الوحيد، فأعِد قراءةَ الفجوة وقسمَها"
    )

    # مُشغَّلٌ باليد: مدخلُه `main` بوسيطٍ إلزاميّ، لا دالّةٌ يستدعيها عامل.
    entry = _function(BACKFILL, "main")
    required = {
        node.args[0].value
        for node in ast.walk(entry)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_argument"
        and node.args
        and isinstance(node.args[0], ast.Constant)
    }
    assert "--tenant" in required, (
        "فقد الردمُ وسيطَ المستأجر الإلزاميّ — لم يعد أداةَ مشغّلٍ بالضرورة، أعِد القراءة"
    )


def test_the_backfilled_rows_land_as_suspect_so_they_witness_but_do_not_seed() -> None:
    """ما يصل عبر الردم يصل **شاهداً لا بذرة** — وهذا حدُّ صدقِ الجسر.

    `SOIL-MOISTURE-UNIT-IDENTITY-01` يسجّل أنّ `accepted` وحدَها تهيّئ توأمَ المياه،
    و`suspect` تُقارَن ويُنشَر خلافُها ولا تهيّئ. فلو صار الردمُ يكتب `accepted` لتغيّر
    أثرُ الجسر على القرار تغيّراً جوهريّاً بلا أن يقول أحد.
    """
    sql = _sql_text_of_path(BACKFILL, BACKFILL_FUNC)
    assert "'suspect'" in sql, (
        "لم يعد الردمُ يكتب `suspect` — صارت قراءةُ جدول الأجهزة تبلغ القرارَ بوزنٍ آخر، "
        "فأعِد قراءةَ الفجوة وقسمَها قبل البناء عليها"
    )


def _prose_blocks(path: Path) -> list[str]:
    """كلُّ وثيقةٍ وكتلةِ تعليقٍ متّصلة في الملفّ.

    الكتلةُ المتّصلة هي وحدةُ القياس لا السطر: الدعوى الكاذبة كانت موزّعةً على سطرَين
    متجاورَين، فقارئُ السطر الواحد يفوّتها.
    """
    text = path.read_text(encoding="utf-8")
    blocks: list[str] = []

    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node)
            if doc:
                blocks.append(doc)

    current: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            current.append(stripped.lstrip("#").strip())
        elif current:
            blocks.append("\n".join(current))
            current = []
    if current:
        blocks.append("\n".join(current))
    return blocks


#: ملفّاتُ النثر التي وصفت مصدرَ القراءة الزراعيّة وصفاً كاذباً، فصُحِّحت.
PROSE_SURFACE = (
    "api/main.py",
    "api/field_context.py",
    "api/device_registry.py",
    "api/routers/fields.py",
    "api/routers/field_completeness.py",
    "api/routers/devices.py",
    "api/routers/water_twin.py",
)


def test_no_prose_attributes_the_agronomic_reading_to_the_device_table() -> None:
    """الصمتُ صنعه النثر: ستّةُ مواضعَ قالت إنّ القارئَ الزراعيَّ يقرأ جدولَ الأجهزة.

    القاعدةُ المقيسة **ضيّقةٌ بقصد**: تُمنَع مقارنةُ اسمِ القارئ باسم جدول الأجهزة في
    كتلةٍ واحدة. ولا يُمنَع ذكرُ `device_telemetry` نفسُه — فله ذكرٌ **صادق** في
    الشجرة (الكاتبُ وصداه، وبطّاريّةُ التوأم، وأنّ الكاميرا لا تبتلع فيه قياساً).
    ومنعُ الذكر مطلقاً كان سيُحمِّر على دعاوى صحيحة: قارئٌ أوسعُ من دعواه.
    """
    offenders: list[str] = []
    for relative in PROSE_SURFACE:
        path = PLATFORM / relative
        assert path.exists(), f"{relative}: اختفى من الشجرة — حدِّث سطحَ النثر"
        for block in _prose_blocks(path):
            if AGRONOMIC_READER in block and "device_telemetry" in block:
                offenders.append(f"{relative}: {block.strip()[:90]}…")

    assert not offenders, (
        f"نثرٌ ينسب القراءةَ الزراعيّة إلى `device_telemetry` بينما `{AGRONOMIC_READER}` "
        "يقرأ `soil_observations` — وهذا النثرُ بعينه هو ما أخفى العطل:\n  " + "\n  ".join(offenders)
    )
