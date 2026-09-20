"""مصنوعاتُ سجلّ الإثبات التشغيليّ تقول ما قِيس — ولا تدّعي ما لم يُقَس.

شاهدٌ ضيّقٌ على **شكل** المصنوعات لا على سلوك المنتج: يقرأ ملفَّي JSON اللذين يُنتجهما
تشغيلٌ حيٌّ خارج جناح الوحدة (قاعدةٌ حقيقيّة · nats-server حقيقيّ)، ويُثبِت أنّ ما
كُتب فيهما ما يزال يحمل الحقولَ التي بُني عليها السجلّ. مصنوعةٌ تُحرَّر بيدٍ لتُعلن
`production_certified: true` أو لتُخفي اكتشافَ الخطوة ⑤ تُحمِّر هنا.

**ولا يُعيد هذا الملفُّ تشغيلَ القبول**: جناحُ الوحدة لا يملك قاعدةً ولا ناقلاً، وادّعاءُ
قياسٍ هنا كان سيكون «أخضرَ عن سؤالٍ لم يُطرَح».
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence"
LOG = EVIDENCE / "operational_evidence_log.md"
OUTBOX = EVIDENCE / "outbox_nats_isolated_acceptance.json"
RUNTIME = EVIDENCE / "ai_runtime_wiring_live_certification.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_no_local_artefact_claims_production_certification() -> None:
    """حدُّ قبول V25: «لا تسجّل production_certified لهذا الاختبار المحلي»."""
    for path in (OUTBOX, RUNTIME):
        data = _load(path)
        assert data.get("production_certified") is not True, path.name
    outbox = _load(OUTBOX)
    assert outbox["acceptance"]["production_certified"] is False


def test_the_outbox_acceptance_reached_the_consumer_and_was_acked() -> None:
    d = _load(OUTBOX)
    assert d["step2_relay"]["outbox"]["status"] == "sent"
    assert d["step2_relay"]["processed_events_claim"] == "outbox_relay"
    assert d["step3_consume_ack"]["matches_emitted"] is True
    assert d["step3_consume_ack"]["consumer_ack_pending_after_ack"] == 0


def test_redelivery_did_not_duplicate_the_business_effect() -> None:
    """رنبوك V25 §٨: «إعادة التسليم يجب ألا تكرر الأثر التجاري»."""
    d = _load(OUTBOX)["step4_redelivery"]
    assert d["business_effect_duplicated"] is False
    assert d["publish_calls_added"] == 0
    assert d["attempt_outcomes"] == ["published", "skipped"]


def test_the_uncovered_subject_finding_is_recorded_not_hidden() -> None:
    """الاكتشافُ المقيس يبقى في المصنوعة: `sent` بلا دفقٍ يحفظ الرسالة."""
    d = _load(OUTBOX)["step5_uncovered_subject_finding"]
    assert d["worker_marked"] == "sent"
    assert d["covered_by_any_stream"] is False
    assert d["last_error"] is None, "لو ظهر خطأٌ لكان الفقدُ مرئيّاً — الاكتشافُ هو صمتُه"
    assert _load(OUTBOX)["step2_relay"]["pubacks_received_by_publisher"] == 0


def test_the_acceptance_used_the_platform_image_client_version() -> None:
    """القبولُ يُقاس بإصدار الصورة لا بالأحدث: `services/sahool-platform/api/requirements.txt` يثبّت nats-py."""
    pinned = None
    for line in (
        (ROOT / "services/sahool-platform/api/requirements.txt")
        .read_text(encoding="utf-8")
        .splitlines()
    ):
        if line.startswith("nats-py=="):
            pinned = line.split("==", 1)[1].split()[0]
    assert pinned, "لم يعد المتطلَّب يثبّت nats-py — حدِّث الشاهدَ والسجلّ"
    assert _load(OUTBOX)["identities"]["nats_py"] == pinned


def test_the_log_binds_each_entry_to_its_artefact_and_declares_the_window_unmeasurable() -> None:
    text = LOG.read_text(encoding="utf-8")
    assert OUTBOX.name in text and RUNTIME.name in text
    assert "not_yet_measurable" in text, "نافذةُ الـ١٤ يوماً لا تُقاس قبل مرورها — يجب أن يقولها السجلّ"
    assert "OUTBOX-RELAY-MARKS-SENT-WITHOUT-JETSTREAM-ACK-01" in text
