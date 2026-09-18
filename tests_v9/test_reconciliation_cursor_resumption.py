"""`RECONCILIATION-CURSOR-SKIPS-ROWS-THAT-BECOME-ELIGIBLE-01` — مؤشّرٌ يعبر ما تخطّاه.

**المقيس.** `reconcile_device_telemetry` يستأنف بعلامةِ ماءٍ عليا واحدة
(`telemetry_id > checkpoint`) فوق تيّارٍ **مُرشَّح**: الاستعلام يُسقط قراءاتِ الأجهزة
غيرِ المرتبطة بحقل (`d.field_id IS NOT NULL`)، والحلقةُ تتخطّى الأنواعَ التي لا محوّلَ
لها. وفي الحالتين يتقدّم المؤشّرُ بقراءةٍ **لاحقةٍ** مؤهّلة، فيعبر فوق السابقة.

فإذا زال سببُ التخطّي — رُبط الجهازُ بحقل، أو أُضيف محوّلُ النوع — بقيت القراءةُ
القديمة خلف المؤشّر و**لا تعود إليها جولةٌ عاديّةٌ أبداً**. الشرطُ `>` كاذبٌ لها إلى
الأبد.

**ما يُثبِته هذا الملفّ وما لا يُثبِته.** يُثبِت **فقدَ فرصةِ المعالجة في المسار
العاديّ**. ولا يُثبِت حذفَ القراءة الخام (هي باقيةٌ في `device_telemetry`)، ولا أنّ
السيناريو وقع في بيانات إنتاج.

**والنتيجةُ الأهمّ: الإصلاحُ الساذج ليس إصلاحاً.** نقلُ
`last_id = max(last_id, row["telemetry_id"])` إلى ما بعد فحص المحوّل **يُبقي العطل**،
لأنّ القراءةَ المدعومةَ اللاحقة ترفع المؤشّرَ فوق السابقة على أيّ حال. فالعلّةُ في
**نموذج الاستئناف** لا في ترتيب سطر: علامةُ ماءٍ عليا واحدةٌ فوق تيّارٍ مُرشَّح تفقد
بالبناء كلَّ صفٍّ تُخطّي لسببٍ قابلٍ للزوال.

**المنهج** (مأخوذٌ من حزمة أدلّة المالك، ٢٠٢٦-٠٩-١٨، وأُقرّ بفضله):
  ① المصدرُ مثبَّتٌ ببصمة blob ويفشل **مغلقاً** إن تغيّر — فلا يُقاس شيءٌ سواه.
  ② تُنفَّذ الدالّةُ **الأصليّة** مستخرَجةً من شجرة النحو، لا نسخةٌ مُعاد كتابتها.
  ③ بديلُ الاتّصال يقرأ محمولاتِ `WHERE` **من نصّ الاستعلام نفسِه** ويرفض أيَّ SQL لا
     يعرفه. فلا يستطيع أن ينحرف صامتاً عن الشيفرة التي يدّعي وصفَها — وهو الموضعُ
     الذي تفشل فيه البدائلُ عادةً.

لا PostgreSQL ولا NATS ولا ادّعاءَ معاملةٍ أو تزامنٍ أو RLS.
"""

from __future__ import annotations

import ast
import asyncio
import copy
import dataclasses
import hashlib
import re
import sys
import types
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/soil/reconcile_historical.py"
REGISTRY = ROOT / "sahool-brain/gaps/registry.md"

GAP_ID = "RECONCILIATION-CURSOR-SKIPS-ROWS-THAT-BECOME-ELIGIBLE-01"
#: بصمةُ blob للمصدر الذي قِيس. تغيُّرُها يُفشِل الشاهدَ **عمداً**: بديلُ الاتّصال
#: يحاكي محمولاتِ استعلامٍ بعينه، فمصدرٌ آخر يعني وصفاً لم يُراجَع.
PINNED_BLOB = "b7be991ac11bb57f32d1dca5178a369ff6a6ad2c"
TENANT = "00000000-0000-4000-8000-000000000001"
FUTURE_SENSOR = "future_soil_sensor"


def _pinned_source() -> bytes:
    data = SOURCE.read_bytes()
    blob = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()  # noqa: S324 — هويّةُ git لا أمان
    assert blob == PINNED_BLOB, (
        f"{SOURCE.name} تغيّر (blob={blob}) عن اللقطة المقيسة {PINNED_BLOB} — "
        "بديلُ الاتّصال يحاكي محمولاتِ استعلامٍ بعينه، فراجِع الاستعلامَ ثمّ حدِّث البصمة"
    )
    return data


def _load(mutation: str | None = None) -> dict[str, Any]:
    """يُحمّل الدالّةَ الأصليّة من شجرة النحو، مع طفرةٍ اختياريّةٍ مرساةٍ بدقّة."""
    tree = ast.parse(_pinned_source(), filename=str(SOURCE))
    wanted = {"Stats", "_set_tenant", "reconcile_device_telemetry"}
    kept = [
        node
        for node in tree.body
        if getattr(node, "name", None) in wanted
        or (
            isinstance(node, ast.Assign)
            and any(getattr(t, "id", "") == "TELEMETRY_MAP" for t in node.targets)
        )
    ]
    assert len(kept) == 4, f"تغيّرت بنيةُ المصدر (عُقد={len(kept)}) — أعِد قراءةَ الشاهد"
    module_ast = ast.Module(body=copy.deepcopy(kept), type_ignores=[])
    function = next(
        n for n in module_ast.body if getattr(n, "name", "") == "reconcile_device_telemetry"
    )

    if mutation == "move_cursor_below_mapping_check":
        loop = next(
            n
            for n in function.body
            if isinstance(n, ast.For) and isinstance(n.iter, ast.Name) and n.iter.id == "rows"
        )
        cursor, mapping, guard = loop.body[:3]
        assert (
            isinstance(cursor, ast.Assign)
            and getattr(cursor.targets[0], "id", "") == "last_id"
            and isinstance(guard, ast.If)
        ), "انتقل مرساةُ الطفرة — أعِد قراءةَ الحلقة قبل الاستنتاج"
        loop.body[:3] = [mapping, guard, cursor]
    elif mutation is not None:
        raise ValueError(mutation)

    module = types.ModuleType("_pinned_reconcile")
    namespace = module.__dict__
    namespace["dataclass"] = dataclasses.dataclass

    # `@dataclass` يقرأ `sys.modules[cls.__module__].__dict__`، فيلزم تسجيلُ الوحدة
    # مؤقّتاً. والاستعادةُ في `finally` مقصودة: تلويثُ `sys.modules` يبقى نافذاً بقيّةَ
    # الجلسة فيمسّ اختباراتٍ لا شأنَ لها — الصنفُ الذي أُصلح في `service_module.py` (#1017).
    previous = sys.modules.get(module.__name__)
    sys.modules[module.__name__] = module
    try:
        exec(compile(ast.fix_missing_locations(module_ast), str(SOURCE), "exec"), namespace)  # noqa: S102
    finally:
        if previous is None:
            sys.modules.pop(module.__name__, None)
        else:
            sys.modules[module.__name__] = previous
    return namespace


def _norm(sql: str) -> str:
    return " ".join(sql.split())


class _StrictConnection:
    """نموذجٌ علائقيٌّ محدود لهذا الاستعلام وحدَه — لا محاكاةَ PostgreSQL.

    **يرفض أيَّ SQL لا يعرفه.** هذه هي النقطة: بديلٌ يقبل استعلاماً جديداً بصمتٍ
    يصف شيفرةً غيرَ التي يدّعي وصفَها، فيصير الشاهدُ خضرةً كاذبة عن نظامٍ تغيّر.
    """

    def __init__(self, rows: list[dict[str, Any]], fields: dict[str, str | None]):
        self.rows = rows
        self.fields = fields
        self.checkpoint = 0
        self.observations: dict[tuple[str, str], dict[str, Any]] = {}
        self.selects: list[list[int]] = []

    async def fetchval(self, sql: str, tenant: str) -> int:
        expected = (
            "SELECT COALESCE(last_source_id,0) FROM soil_reconciliation_checkpoints "
            "WHERE source_name='device_telemetry' AND tenant_id=$1::uuid"
        )
        assert _norm(sql) == expected and tenant == TENANT, "استعلامُ مؤشّرٍ غيرُ معروف"
        return self.checkpoint

    async def fetch(
        self, sql: str, tenant: str, checkpoint: int, batch: int
    ) -> list[dict[str, Any]]:
        pattern = (
            r"SELECT t\.telemetry_id,t\.device_id,t\.sensor_type,t\.value,t\.unit,"
            r"t\.recorded_at,t\.received_at,d\.field_id "
            r"FROM device_telemetry t JOIN iot_devices d ON d\.device_id=t\.device_id "
            r"WHERE (?P<where>.+) ORDER BY t\.telemetry_id LIMIT \$3"
        )
        parsed = re.fullmatch(pattern, _norm(sql))
        assert parsed and tenant == TENANT and batch >= 1, "استعلامُ اختيارٍ غيرُ معروف"

        # المحمولاتُ تُقرأ **من نصّ المصدر**، فلا يُفترَض محمولٌ لم يكتبه أحد.
        predicates = {
            "t.tenant_id=$1::uuid": lambda r: r["tenant_id"] == tenant,
            "t.telemetry_id>$2": lambda r: r["telemetry_id"] > checkpoint,
            "d.field_id IS NOT NULL": lambda r: r["field_id"] is not None,
        }
        expressions = parsed.group("where").split(" AND ")
        unknown = [e for e in expressions if e not in predicates]
        assert not unknown, f"محمولٌ غيرُ معروف في `WHERE`: {unknown} — لا تُفترَض دلالةٌ جديدة"

        joined = [
            dict(row, field_id=self.fields[row["device_id"]])
            for row in self.rows
            if row["device_id"] in self.fields
        ]
        selected = sorted(
            (r for r in joined if all(predicates[e](r) for e in expressions)),
            key=lambda r: r["telemetry_id"],
        )[:batch]
        self.selects.append([r["telemetry_id"] for r in selected])
        return selected

    async def execute(self, sql: str, *args: Any) -> str:
        text = _norm(sql)
        if text == "SELECT set_config('app.current_tenant', $1, false)":
            return "SELECT 1"
        if text.startswith("INSERT INTO soil_observations("):
            key = (args[1], args[9])
            if key not in self.observations:
                self.observations[key] = {"source_id": args[10]}
            return "INSERT 0 1"
        if text.startswith("INSERT INTO soil_profile_projection_jobs("):
            return "INSERT 0 1"
        if text.startswith("INSERT INTO soil_reconciliation_checkpoints("):
            self.checkpoint = args[1]
            return "INSERT 0 1"
        raise AssertionError(f"كتابةٌ غيرُ معروفة: {text[:80]}")


def _fixture(case: str, *, eligible_from_the_start: bool) -> _StrictConnection:
    moment = datetime(2026, 9, 18, tzinfo=UTC)
    rows = [
        {
            "tenant_id": TENANT,
            "telemetry_id": i,
            "device_id": f"dev_{i}",
            "sensor_type": FUTURE_SENSOR
            if case == "unsupported_type" and i == 10
            else "soil_moisture",
            "value": 25.0,
            "unit": "%",
            "recorded_at": moment,
            "received_at": moment,
        }
        for i in (10, 11)
    ]
    fields: dict[str, str | None] = {"dev_10": "field_A", "dev_11": "field_A"}
    if case == "unbound_device" and not eligible_from_the_start:
        fields["dev_10"] = None
    return _StrictConnection(rows, fields)


def _run(
    case: str, *, mutation: str | None = None, eligible_from_the_start: bool = False
) -> list[int]:
    """يُشغّل جولةً، ثمّ يُزيل سببَ التخطّي، ثمّ جولتَين عاديّتَين. يُعيد ما حُفِظ."""
    program = _load(mutation)
    conn = _fixture(case, eligible_from_the_start=eligible_from_the_start)
    if case == "unsupported_type" and eligible_from_the_start:
        program["TELEMETRY_MAP"][FUTURE_SENSOR] = ("soil_moisture", "%")
    reconcile = program["reconcile_device_telemetry"]

    async def rounds() -> None:
        await reconcile(conn, TENANT, 100)
        # زوالُ سببِ التخطّي: رُبط الجهاز، وأُضيف محوّلُ النوع.
        conn.fields["dev_10"] = "field_A"
        program["TELEMETRY_MAP"][FUTURE_SENSOR] = ("soil_moisture", "%")
        for _ in range(2):
            await reconcile(conn, TENANT, 100)

    asyncio.run(rounds())
    return sorted(v["source_id"] for v in conn.observations.values())


def _gap_status(gap_id: str) -> str:
    text = REGISTRY.read_text(encoding="utf-8")
    start = text.index(f"## {gap_id}")
    section = text[start : text.find("\n## ", start + 1)]
    match = re.search(r"\*\*الحالة:\*\*\s*([a-z]+)", section)
    assert match, f"{gap_id}: لا سطرَ حالة في قسمه"
    return match.group(1)


CASES = ("unbound_device", "unsupported_type")


def test_the_control_shows_both_rows_land_when_they_are_eligible_from_the_start() -> None:
    """ضابطٌ يمنع شاهداً مُرتَّباً ليُظهر الفقدَ دائماً.

    بديلُ اتّصالٍ لا يحفظ شيئاً أبداً كان سيُنتج «فقداً» في كلّ حالة. فيلزم إثباتُ أنّ
    المسارَ **يعمل** حين تتوفّر الأهليّةُ من البداية.
    """
    for case in CASES:
        persisted = _run(case, eligible_from_the_start=True)
        assert persisted == [10, 11], (
            f"{case}: القراءتان مؤهّلتان من البداية ولم تُحفظا ({persisted}) — "
            "الخللُ في الشاهد أو في بديل الاتّصال، لا في المؤشّر"
        )


def test_a_row_skipped_for_a_removable_reason_is_bound_to_the_registry_status() -> None:
    """الفقدُ مقيَّدٌ بالحالة في الاتّجاهين — فالإصلاحُ يُطالِب بالإغلاق ولا يُعاقَب عليه.

    شاهدٌ يؤكّد «القراءةُ 10 تُفقَد» وحدَه يُجمّد العطل عقداً. فالمقيسُ هو الاتّفاق:
    فقدٌ ⇒ الفجوةُ `open`؛ ولا فقدَ ⇒ الحالةُ تُقلَب في الالتزام نفسِه.
    """
    status = _gap_status(GAP_ID)
    for case in CASES:
        persisted = _run(case)
        lost = 10 not in persisted
        if lost:
            assert status == "open", (
                f"{case}: القراءةُ القديمة ما تزال تُفقَد بعد زوال سبب التخطّي "
                f"(المحفوظ {persisted}) والقسمُ يقول `{status}` — إغلاقٌ بلا إصلاح"
            )
        else:
            assert status != "open", (
                f"{case}: صارت القراءةُ القديمة تعود بعد زوال سبب التخطّي "
                f"(المحفوظ {persisted}) والقسمُ ما يزال `open` — اقلب الحالةَ بقياسها"
            )


def test_moving_the_cursor_below_the_mapping_check_is_not_the_fix() -> None:
    """**النتيجةُ التي تمنع إصلاحاً ناقصاً**، وتبقى مقيَّدةً بحالة الفجوة.

    نقلُ رفعِ المؤشّر إلى ما بعد `continue` يبدو إصلاحاً بديهيّاً: «لا يرفع المؤشّرَ
    صفٌّ لم يُحوَّل». لكنّ القراءةَ المدعومةَ **اللاحقة** ترفعه فوق السابقة على أيّ حال،
    فيبقى الفقد. أي أنّ العلّة في **نموذج الاستئناف** لا في ترتيب سطر — وعلامةُ ماءٍ
    عليا واحدةٌ فوق تيّارٍ مُرشَّح تفقد بالبناء كلَّ صفٍّ تُخطّي لسببٍ قابلٍ للزوال.

    مقيسٌ على حزمة أدلّة المالك ومُعادٌ إنتاجُه هنا على الشجرة نفسِها.
    """
    if _gap_status(GAP_ID) != "open":
        pytest.skip("الفجوةُ أُغلقت — أعِد قراءةَ هذه الدعوى على نموذج الاستئناف الجديد")
    persisted = _run("unsupported_type", mutation="move_cursor_below_mapping_check")
    assert 10 not in persisted, (
        f"نقلُ رفع المؤشّر أسفلَ فحص المحوّل صار كافياً وحدَه (المحفوظ {persisted}) — "
        "تغيّر نموذجُ الاستئناف، فأعِد قراءةَ القسم قبل البناء عليه"
    )
