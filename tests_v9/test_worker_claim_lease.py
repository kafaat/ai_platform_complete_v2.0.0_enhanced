"""`WORKER-CLAIM-NOT-PINNED-BY-A-TRANSACTION-01` — المطالبةُ تُثبَّت أو تُكرَّر.

**العطلُ المقيس:** عمّالُ `phase_runtime_workers` كانوا يطالبون بـ`FOR UPDATE SKIP
LOCKED` داخل اتّصالٍ في وضع autocommit وبلا `conn.transaction()` — صفرُ مواضع في
الملفّ كلّه. وفي autocommit يُحرَّر قفلُ الصفّ **فور انتهاء عبارة `SELECT`**، فتصير
المطالبةُ غيرَ مثبَتة ويلتقط عاملٌ ثانٍ الصفوفَ نفسَها.

**وأخطرُ مواضعه `run_actuator_once`:** يطالِب ثمّ ينشر
`sahool.actuator.dispatch.requested` — فالعطلُ ليس مجرّداً، بل **طلبُ إرسالٍ
فيزيائيٍّ مرّتين للأمر نفسه**: حركةُ صمّامٍ أو مضخّةٍ تُطلَب مرّتين.

**وحدُّ صدقٍ مُعلَن:** ما هنا يقيس **بنيةَ الإصلاح** لا سلوكَه على PostgreSQL حيّ.
فالخاصّيّةُ النهائيّة — «عاملان متزامنان لا ينشران الصفَّ نفسَه» — تحتاج قاعدةً
حيّةً بمعاملاتٍ حقيقيّة، وهي في `-m integration` لا هنا. وما يُفرَض هنا أنّ كلَّ
ركنٍ من أركان العلاج الثلاثة موجودٌ في موضعه، وأنّ نزعَ أيٍّ منها يُحمِّر.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

ROOT = Path(__file__).resolve().parents[1]
WORKERS = ROOT / "services" / "sahool-platform" / "api" / "phase_runtime_workers.py"
MIGRATION = ROOT / "migrations" / "v228_worker_claim_lease.sql"

_SRC = WORKERS.read_text(encoding="utf-8")
_TREE = ast.parse(_SRC)

# الجداولُ الستّةُ التي يطالبها العمّال — كلٌّ منها كان موضعَ `SKIP LOCKED` عارياً.
_CLAIMED_TABLES = (
    "runtime_event_outbox",
    "marketplace_plugin_execution_runs",
    "marketplace_plugin_runtime_events",
    "model_promotion_history_runtime",
    "model_rollback_history_runtime",
    "iot_command_dispatch",
)


def _func(name: str) -> ast.AST:
    for node in ast.walk(_TREE):
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"دالّةٌ غائبة: {name}")


def _calls(node: ast.AST) -> set[str]:
    out: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            fn = sub.func
            if isinstance(fn, ast.Name):
                out.add(fn.id)
            elif isinstance(fn, ast.Attribute):
                out.add(fn.attr)
    return out


_WORKERS = (
    "run_outbox_once",
    "run_plugin_once",
    "run_model_registry_once",
    "run_actuator_once",
)


# ── الركنُ الأوّل: لا مطالبةَ عاريةً بعد الآن ────────────────────────────────


def test_no_worker_claims_with_a_bare_skip_locked_anymore():
    """`SKIP LOCKED` العاري كان **هو** العطل — فلا يبقى إلّا داخل المُطالِب الموحَّد.

    والقياسُ على السلاسل الحرفيّة لا على نصّ الملفّ: تعليقٌ يشرح العطلَ يحوي
    العبارةَ نفسَها، فبحثٌ نصّيٌّ كان سيتّهم **توثيق الإصلاح** — وهو ما وقع فعلاً
    في #951: حارسُ الكنس P3.5 أبقى ملفّاً «مخالفاً» بسببِ تعليقٍ يشرح *لماذا* هُجِر
    المُوصّل، فصار توثيقُ الإصلاح مُبطِلاً له.
    """
    holders = [
        fn.name
        for fn in ast.walk(_TREE)
        if isinstance(fn, ast.AsyncFunctionDef | ast.FunctionDef)
        for lit in ast.walk(fn)
        if isinstance(lit, ast.Constant)
        and isinstance(lit.value, str)
        and "FOR UPDATE SKIP LOCKED" in lit.value
    ]
    assert holders == ["claim_batch"], (
        f"مطالبةٌ عاريةٌ خارج المُطالِب الموحَّد: {sorted(set(holders)) or 'لا شيء'}"
    )


def test_every_worker_claims_before_it_publishes():
    """كلُّ عاملٍ يمرّ بـ`claim_batch` — لا استثناء يُنسى بصمت."""
    for name in _WORKERS:
        assert "claim_batch" in _calls(_func(name)), f"{name} لا يُطالِب"


def test_every_worker_finalizes_with_a_compare_and_swap():
    for name in _WORKERS:
        assert "finalize_claim" in _calls(_func(name)), f"{name} لا يُنهي بـCAS"


def test_every_worker_reclaims_expired_leases():
    """بلا استرداد، صفٌّ مُطالَبٌ من عاملٍ انهار يبقى مُطالَباً إلى الأبد.

    فالمطالبةُ تصير قبراً لا إجارة — وهو عطلٌ أهدأُ من التكرار وأطولُ عمراً.
    """
    for name in _WORKERS:
        assert "reclaim_expired" in _calls(_func(name)), f"{name} لا يستردّ الإجارات المنتهية"


# ── الركنُ الثاني: المطالبةُ مثبَّتة، والشبكةُ خارجها ────────────────────────


def test_the_claim_is_pinned_by_an_explicit_transaction():
    """المطالبةُ داخل `conn.transaction()` — وهي الخاصّيّةُ التي كانت غائبةً تماماً.

    كان الملفُّ يحمل **صفرَ** معاملاتٍ صريحة، فكلُّ مطالبةٍ فيه غيرُ مثبَتة.
    """
    assert "conn.transaction()" in _SRC
    claim = _func("claim_batch")
    body = ast.get_source_segment(_SRC, claim) or ""
    assert "claim_token IS NULL" in body, (
        "شرطُ الالتقاط لا يستثني المُطالَب — فالمطالبةُ لا تُخرِج الصفَّ من البِركة"
    )
    assert "gen_random_uuid()" in body, "لا رمزَ مطالبةٍ يُولَّد"


def test_the_network_publish_is_never_inside_a_transaction():
    """درسُ النمط الأوّل (`event_bus.py`): معاملةٌ مفتوحةٌ أثناء I/O شبكيّ تحبس الأقفال.

    فالعلاجُ ليس نقلَ العطل من «مطالبةٌ غيرُ مثبَتة» إلى «أقفالٌ محبوسةٌ أثناء
    الشبكة» — بل فصلُهما. يُقاس بنيويّاً: لا نداءَ `_publish_nats` داخل جسم
    `async with conn.transaction()`.
    """
    for name in _WORKERS:
        for node in ast.walk(_func(name)):
            if isinstance(node, ast.AsyncWith) and "transaction" in (
                ast.get_source_segment(_SRC, node.items[0].context_expr) or ""
            ):
                # **صياغةٌ أولى نجت من طفرتها:** كانت تجمع `ast.Attribute` وحدَه،
                # و`_publish_nats` نداءٌ بـ`ast.Name` — فمرّ الاختبارُ أخضرَ على نشرٍ
                # مزروعٍ داخل معاملة. اختبارٌ يمرّ ليس اختباراً يحرس.
                assert "_publish_nats" not in _calls(node), (
                    f"{name}: نشرٌ شبكيٌّ داخل معاملة — الأقفالُ محبوسةٌ أثناء I/O"
                )


# ── الركنُ الثالث: CAS بوّابةٌ تسبق الأثر الفيزيائيّ ─────────────────────────


def test_the_physical_dispatch_is_gated_on_owning_the_claim():
    """**الخاصّيّةُ التي تمنع حركةَ صمّامٍ مرّتين.**

    `run_actuator_once` يُنهي **قبل** النشر عمداً: لو نُشِر أوّلاً ثمّ سقط الإنهاء
    لعاد الصفُّ إلى البِركة بعد انتهاء الإجارة فيُنشَر طلبٌ فيزيائيٌّ ثانٍ. وبهذا
    الترتيب يكون أسوأُ ما يقع **فقدَ طلب** — وفقدُ طلبٍ أهونُ من تكراره حين يكون
    الطلبُ حركةَ مضخّة (fail-closed).
    """
    body = ast.get_source_segment(_SRC, _func("run_actuator_once")) or ""
    assert "owned and action" in body, "النشرُ الفيزيائيّ غيرُ مشروطٍ بملكيّة المطالبة"
    publish_at = body.index("sahool.actuator.dispatch.requested")
    finalize_at = body.index("finalize_claim")
    assert finalize_at < publish_at, "الإنهاءُ يجب أن يسبق النشر — وإلّا تكرّر الأثر"


# ── الهجرة ──────────────────────────────────────────────────────────────────


def test_the_migration_adds_claim_columns_to_every_claimed_table():
    """عمودٌ ناقصٌ في جدولٍ واحد يجعل عاملَه يسقط عند أوّل مطالبة."""
    sql = MIGRATION.read_text(encoding="utf-8")
    for table in _CLAIMED_TABLES:
        block = re.search(rf"ALTER TABLE {table}\b(.*?);", sql, re.S)
        assert block, f"لا هجرةَ للجدول: {table}"
        for column in ("claim_token", "claimed_by", "lease_until"):
            assert column in block.group(1), f"{table} بلا عمود {column}"


def test_the_migration_is_registered_in_the_manifest():
    """هجرةٌ غيرُ مُسجَّلةٍ لا تُشغَّل — فتسقط الأعمدةُ وتسقط معها العمّال."""
    manifest = (ROOT / "migrations" / "MANIFEST.txt").read_text(encoding="utf-8")
    assert MIGRATION.name in manifest
