"""استشهاداتُ بطاقة M-03 تُقابَل بالشجرة — `CARD-CITES-A-TREE-THAT-MOVED-01`.

**لماذا اختبارٌ لوثيقة:** البطاقةُ ليست سرداً — عليها تُبنى قراراتٌ (أ‑١/أ‑٢ ·
ب‑١/ب‑٣) وتُقاس أثمانُها. ووثيقةٌ تُبنى عليها قراراتٌ ولا يحرسها شيءٌ تنحرف عن
الشجرة صامتةً، فتُقرَأ قياساً وهي ذكرى. و`CLAUDE.md` يشترط «لا معلومة بلا مصدر»
— ولا شيء كان يتحقّق أنّ المصدرَ لا يزال يقول ما نُسِب إليه.

**وليست تثبيتاً للعطل.** لا تؤكّد هذه الحالاتُ أنّ الخللَ قائم؛ تؤكّد أنّ
**الاستشهادَ حيّ**. فإن نُقِل ملفٌّ أو زال نمطٌ، تحمرّ برسالةٍ تقول «أعِد قياسَ
البطاقة» لا «أعِد العطل». وهذا هو الفرقُ الذي كلّف هذا المستودعُ ثمنَه مرّتين:
مرساةٌ تؤكّد بقاءَ العطل تُثبِّت السلوكَ الخاطئ عقداً.

**وقد أثبتت نفسَها فورَ كتابتها:** أوّلُ تشغيلٍ كذّب دعوى البطاقة أنّ الصندوقَ
الميّت هو «الموضعُ الوحيدُ **في الشجرة**» الذي يُديدِب بالمفتاح الصحيح — و`edge.py`
يفعل ذلك أيضاً. صُحِّحت الدعوى إلى «مسار الأوامر»، ولولا هذا الملفّ لبقيت.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

_ROOT = Path(__file__).resolve().parents[1]
_CARD = _ROOT / "docs" / "architecture" / "m03_command_path_adjudication.md"

#: المواضعُ التي تُديدِب على `idempotency_key` في شيفرة الإنتاج. البطاقةُ تحصر
#: الأوّلَ في **مسار الأوامر**؛ والثاني في مسار الحافّة — ووجودُه هو ما أبطل
#: صياغةَ «الوحيد في الشجرة».
_DEDUP_SITES = {
    "services/sahool-platform/api/phase_runtime_store.py",
    "services/sahool-platform/api/routers/edge.py",
}


def _card() -> str:
    return _CARD.read_text(encoding="utf-8")


def test_the_card_exists_and_still_carries_the_measured_section():
    text = _card()
    assert "٣أ)" in text, "قسمُ القياس ٣أ زال من البطاقة — الاستشهاداتُ أدناه تحرس فراغاً"


def test_every_source_file_the_card_cites_still_exists():
    """ملفٌّ مذكورٌ ولا وجود له يجعل السطرَ الذي يستشهد به غيرَ قابلٍ للمراجعة."""
    cited = {
        m for m in re.findall(r"`([a-zA-Z0-9_\-/]+\.(?:py|sql|json|yml))`", _card()) if "/" in m
    }
    missing = sorted(p for p in cited if not (_ROOT / p).exists())
    assert not missing, f"البطاقةُ تستشهد بملفّاتٍ معدومة: {missing}"


def test_the_dedup_key_sites_are_exactly_the_two_the_card_accounts_for():
    """حصرُ البطاقة يجب أن يُقابَل بالشجرة، لا أن يُقرَأ على علّاته.

    **وهذه الحالةُ بعينها كذّبت الصياغةَ الأولى.** فإن ظهر موضعٌ ثالث أو زال أحدُ
    الاثنين، فحُجّةُ §٣ب عن كلفة أ‑٢ تغيّرت — وتُعاد قراءتُها، ولا تُحدَّث الأرقامُ
    هنا حتّى تخضرّ.
    """
    found = set()
    for path in _ROOT.rglob("*.py"):
        rel = path.relative_to(_ROOT).as_posix()
        if rel.startswith(("tests", "scripts_v9")) or "node_modules" in rel:
            continue
        if "ON CONFLICT (idempotency_key)" in path.read_text(encoding="utf-8", errors="ignore"):
            found.add(rel)
    assert found == _DEDUP_SITES, (
        f"مواضعُ الديدوب بالمفتاح تغيّرت: {sorted(found)} — أعِد قياسَ §٣ب في البطاقة "
        "قبل الاعتماد على حُجّتها عن كلفة أ‑٢"
    )


def test_the_live_dispatch_table_still_lacks_the_retry_key_column():
    """أساسُ §٣أ الثاني. زوالُه يعني أنّ العلاجَ هبط — فتُحدَّث البطاقةُ لا يُعاد العطل."""
    v109 = (_ROOT / "migrations" / "v109_phase9_iot_execution_adapters.sql").read_text(
        encoding="utf-8"
    )
    if "idempotency_key" in v109:
        pytest.fail(
            "v109 صار يحمل `idempotency_key` — وهو العلاجُ الذي تصفه البطاقةُ محجوباً. "
            "حدِّث §٣أ و§٣ب: الحُجّةُ كلُّها مبنيّةٌ على غيابه."
        )
