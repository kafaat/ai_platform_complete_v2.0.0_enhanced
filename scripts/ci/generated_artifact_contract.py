#!/usr/bin/env python3
"""عقد واحد لكلّ حارس يكتب مصنوعة ويفحصها: ارسم ثمّ قارن، ولا تكتب أثناء الفحص.

GENERATED-CHECK-IGNORES-ITS-OWN-COMPANION-ARTIFACTS-01. القياس الذي أنتج هذه الوحدة:
ستّة حرّاس تُشغَّل بـ`--check` في workflows، و**١٣ من ١٦ مصنوعة يملكونها تُفسَد
والفحص أخضر**. ثلاثة منهم لا يحرسون شيئاً ممّا يكتبون البتّة.

والأشكال ثلاثة، مقيسة بإفساد كلّ ملفّ على حدة عند bbfe121f:

  • واحد يستدعي التوليد بلا شرط داخل `main()`، فيكتب الملفّ ثمّ يفحص **ما كتبه
    للتوّ**. إفسادُ الملفّ يُمحى قبل أن يُقرأ — والفحص يقيس نفسه لا الشجرة. وهو
    كذلك يكتب أثناء الفحص (CHECK-STEPS-MUTATE-THE-TREE-01): مقيس بأزمنة التعديل،
    وهو **الوحيد** من الستّة الذي يفعلها — `duplicate_definition_guard` (١ من ١).
  • واثنان لا يكتبان أثناء الفحص، لكنّهما لا يقارنان المصنوعة **إطلاقاً**: يعيدان
    بناء الجرد في الذاكرة، ويؤكّدان قواعدهما الدلاليّة عليه، ولا ينظران إلى الملفّ
    المُلتزَم مرّة — `ai_container_contract_guard` و`runtime_container_deep_contract_guard`
    (٢ من ٢ لكلٍّ). الظنّ الأوّل أنّهما من الصنف السابق؛ القياس كذّبه.
  • وثلاثة تقارن ملفّ `.generated.json` وحده وتترك رفيقيه `.csv` و`.md` بلا حراسة —
    `capability_registry_v1` (٤ من ٥) · `platform_main_subinventory_guard` (٢ من ٣) ·
    `production_certification_checklist_guard` (٢ من ٣).

في الأشكال الثلاثة المصنوعة **مُلتزَمة وتبدو محروسة ولا شيء يراقبها**.

العلاج هنا مُوحَّد عمداً: `render_*` تُنتج النصّ، `write_all` تكتبه، و`drift` تقارنه
بايتاً ببايت بما على القرص. الكتابة والفحص يمرّان بدالّة الرسم **نفسها**، فلا يمكن
أن يتباعد ما يُكتَب عمّا يُقارَن — وهو الفخّ الذي أوقع `capability_linker` سابقاً حين
كُتِبت المصنوعة بترجمة أسطر وقُورنت بغيرها.

المقارنة بالبايت لا بالنصّ المُترجَم: ``read_text`` يُوحّد نهايات الأسطر، فيُخفي
إفساداً حقيقيّاً في ملفّ CSV تنتهي أسطره بـCRLF. المقارنة الصادقة هي ما يراه git.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Artifact:
    """مصنوعة مولَّدة: مسارها والنصّ الذي يجب أن تحمله."""

    path: Path
    text: str

    @property
    def rel(self) -> str:
        try:
            return self.path.relative_to(ROOT).as_posix()
        except ValueError:
            return str(self.path)


def render_json(payload: object, *, indent: int = 2) -> str:
    """JSON بنفس الشكل الذي تكتبه الحرّاس: مسافة بادئة، unicode كما هو، سطر ختاميّ."""
    return json.dumps(payload, ensure_ascii=False, indent=indent) + "\n"


def render_csv(rows: list[dict], fieldnames: list[str] | None = None) -> str:
    """CSV حتميّ بـLF، مطابق عبر المنصات ولا يُنتج trailing whitespace في Git."""
    if not rows:
        return ""
    names = fieldnames if fieldnames is not None else list(rows[0].keys())
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=names, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def write_all(artifacts: list[Artifact]) -> None:
    """يكتب كلّ مصنوعة — يُستدعى تحت علم الكتابة وحده، لا في الفحص."""
    for artifact in artifacts:
        artifact.path.parent.mkdir(parents=True, exist_ok=True)
        artifact.path.write_bytes(artifact.text.encode("utf-8"))


def drift(artifacts: list[Artifact]) -> list[str]:
    """المصنوعات التي لا يُطابق محتواها على القرص ما يُنتجه المولّد الآن.

    الغياب انحراف أيضاً: مصنوعة مُعلَنة وغير موجودة ليست «لا شيء يُقارَن» بل ملفّ
    مفقود يجب أن يُسمّى.
    """
    drifting: list[str] = []
    for artifact in artifacts:
        expected = artifact.text.encode("utf-8")
        try:
            actual = artifact.path.read_bytes()
        except OSError:
            drifting.append(f"{artifact.rel} (مفقود)")
            continue
        if actual != expected:
            drifting.append(artifact.rel)
    return drifting


def enforce(artifacts: list[Artifact], *, write: bool, label: str) -> None:
    """العقد كاملاً في سطرين: اكتب تحت العلم، وقارن تحت الفحص.

    يرفع ``SystemExit`` مُسمّياً كلّ ملفّ منحرف. لا يكتب شيئاً حين ``write=False`` —
    فالفحص قراءة، والحارس الذي يُصلح ما يفحصه لا يفحص شيئاً.
    """
    if write:
        write_all(artifacts)
        return
    drifting = drift(artifacts)
    if drifting:
        raise SystemExit(
            f"{label}: انحراف مصنوعات مولَّدة — " + " · ".join(drifting) + "\n"
            "المحتوى المُلتزَم لا يُطابق ما يُنتجه المولّد. أعد التوليد بعلم الكتابة "
            "وراجع الفرق قبل الالتزام."
        )
