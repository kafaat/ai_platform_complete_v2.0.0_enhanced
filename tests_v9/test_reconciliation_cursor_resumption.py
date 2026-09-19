"""`RECONCILIATION-CURSOR-SKIPS-ROWS-THAT-BECOME-ELIGIBLE-01` — نموذجُ الاستئناف.

**العطلُ الذي أُصلح.** `reconcile_device_telemetry` كان يستأنف بعلامةِ ماءٍ عليا واحدة
(`telemetry_id > checkpoint`) فوق تيّارٍ **مُرشَّح**: الاستعلام يُسقط قراءاتِ الأجهزة
غيرِ المرتبطة بحقل، والحلقةُ تتخطّى الأنواعَ التي لا محوّلَ لها. وفي الحالتين يتقدّم
المؤشّرُ بقراءةٍ **لاحقةٍ** مؤهّلة فيعبر فوق السابقة، فإذا زال سببُ التخطّي بقيت خلفه
ولا تعود إليها جولةٌ أبداً.

**والعلاجُ ليس مؤشّراً يتوقّف.** مؤشّرٌ يرفض تجاوزَ صفٍّ غيرِ محسوم يُجمّد المصالحةَ
كلَّها عند أوّل نوعٍ لن يُحوَّل أبداً — **تقدّمٌ مستحيل**، وهو صنفُ «حارسٍ لا يقبل حالةً
صادقة» المُغلَق في #1026. فالمؤشّرُ يبقى يتقدّم، و**ما تجاوزه يُكتَب** بسببه في
`soil_reconciliation_deferrals` (v231)، وكلُّ جولةٍ تُعيد فحصَ المؤجَّلات قبل المسح.

**ما يُثبِته هذا الملفّ وما لا يُثبِته.** يُثبِت أنّ **فرصةَ المعالجة تعود** حين يزول
السبب، وأنّ التقدّمَ لا يتوقّف حين لا يزول. ولا يُثبِت سلوكَ المعاملة ولا RLS ولا
التزامن — لا قاعدةَ بياناتٍ هنا. **القبولُ الحيُّ موضعُه**
`tests_v9/test_reconciliation_resumption_live_pg.py` على PostgreSQL حيّ داخل وظيفة
*Integration Tests*.

**المنهج** (مأخوذٌ من حزمة أدلّة المالك، ٢٠٢٦-٠٩-١٨، وأُقرّ بفضله):
  ① المصدرُ مثبَّتٌ ببصمة blob ويفشل **مغلقاً** إن تغيّر — فلا يُقاس شيءٌ سواه.
  ② تُنفَّذ الدوالُّ **الأصليّة** مستخرَجةً من شجرة النحو، لا نسخةٌ مُعاد كتابتها.
  ③ بديلُ الاتّصال يقرأ محمولاتِ `WHERE` **من نصّ الاستعلام نفسِه** ويرفض أيَّ SQL لا
     يعرفه. فلا يستطيع أن ينحرف صامتاً عن الشيفرة التي يدّعي وصفَها.
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
#: يحاكي محمولاتِ استعلاماتٍ بعينها، فمصدرٌ آخر يعني وصفاً لم يُراجَع.
PINNED_BLOB = "3c5460b644fbcf45437ca494a1a24c5690435344"
TENANT = "00000000-0000-4000-8000-000000000001"
FUTURE_SENSOR = "future_soil_sensor"
SOURCE_NAME = "device_telemetry"

#: العُقدُ التي يحتاجها التنفيذ. قائمةٌ صريحة لا `exec` للملفّ كلِّه: استيرادُ
#: `asyncpg` و`argparse` هنا يجرّ تبعيّاتٍ لا شأنَ للقياس بها.
_WANTED = {
    "Stats",
    "_set_tenant",
    "_defer",
    "_resolve_deferral",
    "_open_deferrals",
    "_process_telemetry_row",
    "reconcile_device_telemetry",
}
_WANTED_ASSIGNS = {"TELEMETRY_MAP", "DEFERRAL_REASONS", "_TELEMETRY_COLUMNS"}


def _pinned_source() -> bytes:
    data = SOURCE.read_bytes()
    blob = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()  # noqa: S324 — هويّةُ git لا أمان
    assert blob == PINNED_BLOB, (
        f"{SOURCE.name} تغيّر (blob={blob}) عن اللقطة المقيسة {PINNED_BLOB} — "
        "بديلُ الاتّصال يحاكي محمولاتِ استعلاماتٍ بعينها، فراجِعها ثمّ حدِّث البصمة"
    )
    return data


def _load(mutation: str | None = None) -> dict[str, Any]:
    """يُحمّل الدوالَّ الأصليّة من شجرة النحو، مع طفرةٍ اختياريّةٍ مرساةٍ بدقّة."""
    tree = ast.parse(_pinned_source(), filename=str(SOURCE))
    kept = [
        node
        for node in tree.body
        if getattr(node, "name", None) in _WANTED
        or (
            isinstance(node, ast.Assign)
            and any(getattr(t, "id", "") in _WANTED_ASSIGNS for t in node.targets)
        )
    ]
    expected = len(_WANTED) + len(_WANTED_ASSIGNS)
    assert len(kept) == expected, f"تغيّرت بنيةُ المصدر (عُقد={len(kept)}/{expected})"
    module_ast = ast.Module(body=copy.deepcopy(kept), type_ignores=[])

    if mutation == "never_record_the_deferral":
        # نزعُ السجلّ: يعود المؤشّرُ علامةَ ماءٍ عليا فوق تيّارٍ مُرشَّح — العطلُ الأصليّ.
        function = next(
            n for n in module_ast.body if getattr(n, "name", "") == "reconcile_device_telemetry"
        )
        # **استبدالٌ في الموضع لا حذفٌ بمسحٍ عامّ.** أوّلُ صياغةٍ رشّحت *كلّ* حقلٍ من
        # نوع list في الشجرة، فطالت `arguments.args` (وهي قائمةُ عُقد `arg`) واستبدلتها
        # بـ`Pass` ⇒ `TypeError: required field "arg" missing from arg`. الطفرةُ التي
        # تُتلِف الشجرةَ لا تقيس شيئاً؛ فالمرساةُ الآن العقدةُ نفسُها.
        replaced = 0
        for parent in ast.walk(function):
            for _field, value in ast.iter_fields(parent):
                if not isinstance(value, list):
                    continue
                for index, node in enumerate(value):
                    if (
                        isinstance(node, ast.Expr)
                        and isinstance(node.value, ast.Await)
                        and getattr(getattr(node.value.value, "func", None), "id", "") == "_defer"
                    ):
                        value[index] = ast.Pass()
                        replaced += 1
        assert replaced == 2, f"مرساةُ `_defer` انتقلت (استُبدِل {replaced} لا 2)"
    elif mutation == "never_reexamine":
        # نزعُ المرور الأوّل: تُكتَب المؤجَّلاتُ ولا يُعاد فحصُها — سجلٌّ لا يُقرأ.
        function = next(
            n for n in module_ast.body if getattr(n, "name", "") == "reconcile_device_telemetry"
        )
        guard = next(
            n
            for n in function.body
            if isinstance(n, ast.If) and getattr(n.test, "id", "") == "deferred_ids"
        )
        guard.test = ast.Constant(value=False)
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


_SELECT_SHAPE = (
    r"SELECT t\.telemetry_id,t\.device_id,t\.sensor_type,t\.value,t\.unit,"
    r"t\.recorded_at,t\.received_at, d\.device_id AS joined_device_id, d\.field_id "
    r"FROM device_telemetry t LEFT JOIN iot_devices d ON d\.device_id=t\.device_id "
)


class _StrictConnection:
    """نموذجٌ علائقيٌّ محدود لهذه الاستعلامات وحدَها — لا محاكاةَ PostgreSQL.

    **يرفض أيَّ SQL لا يعرفه.** هذه هي النقطة: بديلٌ يقبل استعلاماً جديداً بصمتٍ
    يصف شيفرةً غيرَ التي يدّعي وصفَها، فيصير الشاهدُ خضرةً كاذبة عن نظامٍ تغيّر.
    """

    def __init__(self, rows: list[dict[str, Any]], devices: dict[str, str | None]):
        self.rows = rows
        #: `devices` يحمل الأجهزةَ **المسجَّلة** وحدَها. جهازٌ غائبٌ من هذا القاموس
        #: غيرُ مسجَّل، وهو ما كان `JOIN` الداخليُّ القديم يُخفيه تماماً.
        self.devices = devices
        self.checkpoint = 0
        self.observations: dict[tuple[str, str], dict[str, Any]] = {}
        self.deferrals: dict[int, dict[str, Any]] = {}
        self.selects: list[list[int]] = []
        self.reexamined: list[list[int]] = []

    # ── القراءة ────────────────────────────────────────────────────────────────
    def _joined(self) -> list[dict[str, Any]]:
        return [
            dict(
                row,
                joined_device_id=row["device_id"] if row["device_id"] in self.devices else None,
                field_id=self.devices.get(row["device_id"]),
            )
            for row in self.rows
        ]

    async def fetchval(self, sql: str, tenant: str) -> int:
        expected = (
            "SELECT COALESCE(last_source_id,0) FROM soil_reconciliation_checkpoints "
            "WHERE source_name='device_telemetry' AND tenant_id=$1::uuid"
        )
        assert _norm(sql) == expected and tenant == TENANT, "استعلامُ مؤشّرٍ غيرُ معروف"
        return self.checkpoint

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        text = _norm(sql)

        if text.startswith("SELECT source_id FROM soil_reconciliation_deferrals"):
            source, tenant, limit = args
            assert source == SOURCE_NAME and tenant == TENANT and limit >= 1
            assert "resolved_at IS NULL" in text, (
                "قراءةُ المؤجَّلات بلا شرطِ `resolved_at IS NULL` تُعيد فحصَ ما حُسِم"
            )
            open_ids = sorted(k for k, v in self.deferrals.items() if v["resolved_at"] is None)
            return [{"source_id": i} for i in open_ids[:limit]]

        parsed = re.fullmatch(_SELECT_SHAPE + r"WHERE (?P<where>.+?)(?P<tail> LIMIT \$3)?", text)
        assert parsed, f"استعلامُ اختيارٍ غيرُ معروف: {text[:120]}"
        where = parsed.group("where").replace(" ORDER BY t.telemetry_id", "")

        # المحمولاتُ تُقرأ **من نصّ المصدر**، فلا يُفترَض محمولٌ لم يكتبه أحد.
        if " = ANY($2::bigint[])" in where:  # المرورُ الأوّل: إعادةُ فحصِ المؤجَّلات
            tenant, ids = args
            assert tenant == TENANT
            assert where == "t.tenant_id=$1::uuid AND t.telemetry_id = ANY($2::bigint[])", where
            selected = sorted(
                (
                    r
                    for r in self._joined()
                    if r["tenant_id"] == tenant and r["telemetry_id"] in ids
                ),
                key=lambda r: r["telemetry_id"],
            )
            self.reexamined.append([r["telemetry_id"] for r in selected])
            return selected

        tenant, checkpoint, batch = args  # المرورُ الثاني: المسحُ إلى الأمام
        assert tenant == TENANT and batch >= 1
        predicates = {
            "t.tenant_id=$1::uuid": lambda r: r["tenant_id"] == tenant,
            "t.telemetry_id>$2": lambda r: r["telemetry_id"] > checkpoint,
            # **لا `d.field_id IS NOT NULL` هنا بعد الآن.** بقاؤه يعني أنّ الصفَّ غيرَ
            # المؤهّل لا يُرى، وما لا يُرى لا يُكتَب — وهو العطلُ بعينه.
            "d.field_id IS NOT NULL": lambda r: r["field_id"] is not None,
        }
        expressions = where.split(" AND ")
        unknown = [e for e in expressions if e not in predicates]
        assert not unknown, f"محمولٌ غيرُ معروف في `WHERE`: {unknown} — لا تُفترَض دلالةٌ جديدة"
        selected = sorted(
            (r for r in self._joined() if all(predicates[e](r) for e in expressions)),
            key=lambda r: r["telemetry_id"],
        )[:batch]
        self.selects.append([r["telemetry_id"] for r in selected])
        return selected

    # ── الكتابة ────────────────────────────────────────────────────────────────
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
        if text.startswith("INSERT INTO soil_reconciliation_deferrals("):
            source, tenant, source_id, reason = args
            assert source == SOURCE_NAME and tenant == TENANT
            entry = self.deferrals.setdefault(
                source_id, {"reason": reason, "examinations": 0, "resolved_at": None}
            )
            entry["reason"] = reason
            entry["examinations"] += 1
            return "INSERT 0 1"
        if text.startswith("UPDATE soil_reconciliation_deferrals"):
            source, tenant, source_id = args
            assert source == SOURCE_NAME and tenant == TENANT
            entry = self.deferrals.get(source_id)
            if entry and entry["resolved_at"] is None:
                entry["resolved_at"] = "resolved"
                entry["examinations"] += 1
            return "UPDATE 1"
        raise AssertionError(f"كتابةٌ غيرُ معروفة: {text[:80]}")


# ── الحالات ─────────────────────────────────────────────────────────────────────
#: كلُّ حالةٍ: سببُ تخطٍّ مختلف للقراءة `10`، والقراءة `11` مؤهّلةٌ دائماً فترفع المؤشّر
#: فوق `10` — وهي الآليّةُ التي كانت تُضيعها.
CASES = ("unbound_device", "unsupported_type", "unregistered_device")
REASON_OF = {
    "unbound_device": "device_field_unbound",
    "unsupported_type": "sensor_type_unmapped",
    "unregistered_device": "device_not_registered",
}


def _fixture(case: str, *, eligible_from_the_start: bool) -> _StrictConnection:
    moment = datetime(2026, 9, 19, tzinfo=UTC)
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
    devices: dict[str, str | None] = {"dev_10": "field_A", "dev_11": "field_A"}
    if not eligible_from_the_start:
        if case == "unbound_device":
            devices["dev_10"] = None
        elif case == "unregistered_device":
            del devices["dev_10"]
    return _StrictConnection(rows, devices)


def _run(
    case: str, *, mutation: str | None = None, eligible_from_the_start: bool = False
) -> dict[str, Any]:
    """جولةٌ، ثمّ إزالةُ سببِ التخطّي، ثمّ جولتان عاديّتان. يُعيد ما حُفِظ وما سُجِّل."""
    program = _load(mutation)
    conn = _fixture(case, eligible_from_the_start=eligible_from_the_start)
    if case == "unsupported_type" and eligible_from_the_start:
        program["TELEMETRY_MAP"][FUTURE_SENSOR] = ("soil_moisture", "%")
    reconcile = program["reconcile_device_telemetry"]

    async def rounds() -> list[Any]:
        first = await reconcile(conn, TENANT, 100)
        # زوالُ سببِ التخطّي: سُجِّل الجهاز، ورُبط بحقل، وأُضيف محوّلُ النوع.
        conn.devices["dev_10"] = "field_A"
        program["TELEMETRY_MAP"][FUTURE_SENSOR] = ("soil_moisture", "%")
        return [first, *[await reconcile(conn, TENANT, 100) for _ in range(2)]]

    stats = asyncio.run(rounds())
    return {
        "persisted": sorted(v["source_id"] for v in conn.observations.values()),
        "deferrals": conn.deferrals,
        "selects": conn.selects,
        "reexamined": conn.reexamined,
        "stats": [dataclasses.asdict(s) for s in stats],
    }


def _gap_status(gap_id: str) -> str:
    text = REGISTRY.read_text(encoding="utf-8")
    start = text.index(f"## {gap_id}")
    section = text[start : text.find("\n## ", start + 1)]
    match = re.search(r"\*\*الحالة:\*\*\s*([a-z]+)", section)
    assert match, f"{gap_id}: لا سطرَ حالة في قسمه"
    return match.group(1)


# ── ① الضابط: المسارُ يعمل أصلاً ────────────────────────────────────────────────


def test_the_control_shows_both_rows_land_when_they_are_eligible_from_the_start() -> None:
    """ضابطٌ يمنع شاهداً مُرتَّباً ليُظهر النتيجةَ المرجوّة دائماً.

    بديلُ اتّصالٍ لا يحفظ شيئاً أبداً — أو يحفظ كلَّ شيءٍ دائماً — كان سيُعطي الحكمَ
    نفسَه في كلّ حالة. فيلزم إثباتُ أنّ المسارَ يعمل حين تتوفّر الأهليّةُ من البداية،
    و**بلا تأجيلٍ واحد**.
    """
    for case in CASES:
        result = _run(case, eligible_from_the_start=True)
        assert result["persisted"] == [10, 11], f"{case}: {result['persisted']}"
        assert result["deferrals"] == {}, (
            f"{case}: سُجِّل تأجيلٌ لصفٍّ مؤهّلٍ من البداية — {result['deferrals']}"
        )


# ── ② الإصلاح: الفرصةُ تعود ─────────────────────────────────────────────────────


@pytest.mark.parametrize("case", CASES)
def test_a_row_passed_for_a_removable_reason_is_recovered_after_the_reason_clears(case) -> None:
    """جوهرُ الشريحة: ما تجاوزه المؤشّرُ كُتِب، فعادت إليه جولةٌ لاحقة.

    والسببُ يُسجَّل بعينه لا «تعذّر»: إعادةُ الفحص تقرؤه، وتقريرُ المشغّل يقرؤه،
    وسببٌ واحدٌ عامّ كان سيجعل الجدولَ عدّاداً لا سجلّاً.
    """
    result = _run(case)
    assert 10 in result["persisted"], (
        f"{case}: القراءةُ 10 لم تُستردَّ بعد زوال السبب — {result['stats']}"
    )
    assert result["deferrals"][10]["reason"] == REASON_OF[case]
    assert result["deferrals"][10]["resolved_at"] is not None, "حُوسِبت ولم تُحسَم"
    assert result["reexamined"] and 10 in result["reexamined"][0], (
        "لم تُعَد قراءةُ 10 إلى الفحص — المرورُ الأوّل لم يرَها"
    )


def test_a_resolved_deferral_is_kept_not_deleted() -> None:
    """الحسمُ يُوسَم ولا يُمحى.

    جدولٌ يُحذَف منه عند النجاح يجعل الفراغَ يعني **شيئين**: «لم يُؤجَّل شيءٌ قطّ»
    و«أُسقط كلُّ شيءٍ بصمت». وهو بالضبط صنفُ اللبس الذي وُجِد هذا الجدولُ لإزالته.
    """
    result = _run("unbound_device")
    assert 10 in result["deferrals"], "المدخلُ اختفى بعد الحسم"
    assert result["deferrals"][10]["examinations"] >= 2, "عدّادُ الفحص لا يتقدّم"


# ── ③ التقدّمُ لا يتوقّف — الحالةُ التي تجعل العلاجَ عطلاً لو أُغفِلت ───────────


def test_a_reason_that_never_clears_does_not_stall_later_rows() -> None:
    """**المقابلُ الضروريّ.** مؤشّرٌ يتوقّف عند أوّل صفٍّ غيرِ محسوم كان يجعل نوعاً
    واحداً لن يُحوَّل أبداً يُجمّد المصالحةَ كلَّها — تقدّمٌ مستحيل، وهو صنفُ «حارسٍ لا
    يقبل حالةً صادقة» (#1026) في ثوب مُصالِح.

    هنا: سببُ `10` لا يزول أبداً، ومع ذلك تمرّ `11` وتُحفَظ ويتقدّم المؤشّر.
    """
    program = _load()
    conn = _fixture("unsupported_type", eligible_from_the_start=False)
    reconcile = program["reconcile_device_telemetry"]

    async def rounds() -> list[Any]:
        return [await reconcile(conn, TENANT, 100) for _ in range(3)]

    stats = asyncio.run(rounds())
    persisted = sorted(v["source_id"] for v in conn.observations.values())
    assert persisted == [11], f"التقدّمُ توقّف أو تسرّب: {persisted}"
    assert conn.checkpoint == 11, f"المؤشّرُ لم يتقدّم ({conn.checkpoint}) — مصالحةٌ مجمّدة"
    assert conn.deferrals[10]["resolved_at"] is None
    assert conn.deferrals[10]["examinations"] >= 3, "السببُ باقٍ ولا يُعاد فحصُه — سجلٌّ يُكتَب ولا يُقرأ"
    assert [dataclasses.asdict(s)["deferred"] for s in stats][0] == 1


# ── ④ الربطُ بحالة السجلّ، جامعاً لا منفرداً (#1026) ────────────────────────────


def test_recovery_across_all_cases_is_bound_to_the_registry_status() -> None:
    """حالةٌ واحدة للفجوة الجامعة، تُقاس الحالاتُ كلُّها **ثمّ** يُحكَم مرّةً واحدة.

    الربطُ المنفرد يرفض الإصلاحَ الجزئيّ برفضِ الحالتين معاً — عطلُ #1025 الذي
    أصلحته #1026. فبقاءُ فقدٍ في أيّ حالةٍ يُبقي الفجوةَ `open`، وزوالُه في الجميع
    يستلزم حالةً غيرَ `open`.
    """
    status = _gap_status(GAP_ID)
    outcomes = {case: _run(case)["persisted"] for case in CASES}
    lost = [case for case, persisted in outcomes.items() if 10 not in persisted]
    if lost:
        assert status == "open", f"الفقدُ باقٍ في {lost} والقسم يقول `{status}` — {outcomes}"
    else:
        assert status != "open", f"عاد كلُّ ما فُقِد والقسم ما زال `open` — {outcomes}"


@pytest.mark.parametrize("status", ["open", "fixed"])
@pytest.mark.parametrize(
    "lost_cases",
    [(), ("unbound_device",), ("unsupported_type",), CASES],
    ids=["neither", "unbound-only", "unsupported-only", "all"],
)
def test_registry_binding_aggregates_all_witness_cases(monkeypatch, status, lost_cases) -> None:
    """يقيس **حكمَ الربط** بنتائج معلومة، لا الاستئنافَ ولا معاملاتِ القاعدة."""
    examined: list[str] = []

    def measured(case, **_kwargs):
        examined.append(case)
        return {"persisted": [11] if case in lost_cases else [10, 11]}

    monkeypatch.setitem(globals(), "_run", measured)
    monkeypatch.setitem(globals(), "_gap_status", lambda _: status)
    verdict = test_recovery_across_all_cases_is_bound_to_the_registry_status
    if (status == "open") == bool(lost_cases):
        verdict()
    else:
        with pytest.raises(AssertionError):
            verdict()
    assert examined == list(CASES), "يجب قياسُ كلّ الحالات قبل حكم الفجوة الجامعة"
