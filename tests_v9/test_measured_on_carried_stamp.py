"""ختمُ ``measured_on`` يتبع آخرَ قياسٍ غيّر الحمولة لا ``HEAD``.

``DOCS-ONLY-PR-RESTAMPED-INTO-REPORT-ONLY-BY-REGENERATION-01`` — أُمسِك على #1118 وأُعيد
إنتاجُه على #1123: ``verify_all_generated --fix`` على صيانة دماغٍ بحتة كان يختم السطرَ
نفسه في ستّة ملفّات، فيحجب ``no_report_only_change_guard`` الـPR الوثائقيّ.

الشواهدُ هنا سلوكيّة: تُشغِّل الدالّةَ ومولِّداً حقيقيّاً على ملفّاتٍ مؤقّتة، ولا تقرأ نصَّ
المصدر. والحدُّ الذي يحرسه آخرُها: **الحمولةُ المتغيّرة تُعيد الختم** — فالثباتُ لا يصير
إخفاءً للبيات.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / "scripts" / "ci"
OLD = "a" * 40
NEW = "b" * 40


def _load(name: str):
    if str(CI) not in sys.path:
        sys.path.insert(0, str(CI))
    spec = importlib.util.spec_from_file_location(f"_carried_{name}", CI / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write(path: Path, document: dict) -> None:
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_an_unchanged_payload_keeps_the_previous_stamp(tmp_path: Path) -> None:
    dt = _load("deterministic_time")
    target = tmp_path / "artifact.json"
    _write(target, {"measured_on": OLD, "count": 3, "rows": ["x", "y"]})

    assert (
        dt.carried_stamp(target, {"measured_on": NEW, "count": 3, "rows": ["x", "y"]}, NEW) == OLD
    )


def test_a_changed_payload_takes_the_fresh_stamp(tmp_path: Path) -> None:
    dt = _load("deterministic_time")
    target = tmp_path / "artifact.json"
    _write(target, {"measured_on": OLD, "count": 3})

    assert dt.carried_stamp(target, {"measured_on": NEW, "count": 4}, NEW) == NEW


def test_a_hand_decided_field_change_is_a_payload_change(tmp_path: Path) -> None:
    """``proven_live`` قرارٌ بخطّ اليد يحمله المولّد قُدُماً — تغيّرُه ليس «ختماً فقط».

    هذا ما كان يُخشى من توسيع قائمة المصنوعات: أن يمرّ تعديلُ حقلِ تحكيمٍ خلف ختمٍ آليّ.
    هنا لا يمرّ: الختمُ يتجدّد، والملفُّ يبقى خارج المصنوعات في الحارس كما هو.
    """
    dt = _load("deterministic_time")
    target = tmp_path / "debt_baseline.json"
    _write(target, {"measured_on": OLD, "proven_live": {}, "claiming_db_enforced": ["t.py"]})

    edited = {"measured_on": NEW, "proven_live": {"t.py": "live"}, "claiming_db_enforced": ["t.py"]}
    assert dt.carried_stamp(target, edited, NEW) == NEW


def test_key_order_and_whitespace_are_not_payload(tmp_path: Path) -> None:
    dt = _load("deterministic_time")
    target = tmp_path / "artifact.json"
    target.write_text('{"rows":["x"],   "measured_on":"' + OLD + '","count":1}', encoding="utf-8")

    assert dt.carried_stamp(target, {"count": 1, "measured_on": NEW, "rows": ["x"]}, NEW) == OLD


@pytest.mark.parametrize(
    "content",
    [
        None,
        "not json",
        "[1, 2]",
        json.dumps({"count": 1}),
        json.dumps({"measured_on": "", "count": 1}),
    ],
    ids=["missing", "corrupt", "not-a-mapping", "no-stamp", "empty-stamp"],
)
def test_nothing_to_carry_takes_the_fresh_stamp(tmp_path: Path, content: str | None) -> None:
    """لا اختلاقَ ختمٍ من لا شيء: غيابٌ أو تلفٌ أو ختمٌ فارغ ⇒ الطازج."""
    dt = _load("deterministic_time")
    target = tmp_path / "artifact.json"
    if content is not None:
        target.write_text(content, encoding="utf-8")

    assert dt.carried_stamp(target, {"measured_on": NEW, "count": 1}, NEW) == NEW


def test_a_real_generator_does_not_restamp_an_unchanged_measurement(
    tmp_path: Path, monkeypatch
) -> None:
    """المولّدُ الحقيقيّ مرّتين على حمولةٍ ثابتة بـ``HEAD`` مختلف ⇒ الختمُ الأوّل يبقى.

    ``generated_write_targets`` يختم بـ``_head()``؛ يُبدَّل ``HEAD`` بين التشغيلين كما يتبدّل
    بين فرعين، والقياسُ نفسُه ثابت.
    """
    module = _load("generated_write_targets")
    manifest = tmp_path / "generated_write_targets.json"
    monkeypatch.setattr(module, "MANIFEST", manifest)
    monkeypatch.setattr(module, "measure", lambda: ["docs/x.json"])

    monkeypatch.setattr(module, "_head", lambda: OLD)
    assert module.generate() == 0
    monkeypatch.setattr(module, "_head", lambda: NEW)
    assert module.generate() == 0

    assert json.loads(manifest.read_text(encoding="utf-8"))["measured_on"] == OLD


def test_a_real_generator_restamps_when_the_measurement_moves(tmp_path: Path, monkeypatch) -> None:
    module = _load("generated_write_targets")
    manifest = tmp_path / "generated_write_targets.json"
    monkeypatch.setattr(module, "MANIFEST", manifest)

    monkeypatch.setattr(module, "measure", lambda: ["docs/x.json"])
    monkeypatch.setattr(module, "_head", lambda: OLD)
    assert module.generate() == 0
    monkeypatch.setattr(module, "measure", lambda: ["docs/x.json", "docs/y.json"])
    monkeypatch.setattr(module, "_head", lambda: NEW)
    assert module.generate() == 0

    assert json.loads(manifest.read_text(encoding="utf-8"))["measured_on"] == NEW
