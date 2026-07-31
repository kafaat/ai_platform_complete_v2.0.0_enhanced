#!/usr/bin/env python3
"""P0-7 — الأثر الفيزيائيّ لا يُطلَق من الدماغ، ولا يُطلَق إلّا من موضع مُسمّى.

المبدأ المُعلَن في `shared/contracts/intelligence_governance.json` وفي خطوة CI
«الدماغ … لا يصل فيزيائيّاً إلّا عبر Decision-Service». كان **مُعلَناً لا مفروضاً**
إلّا جزئيّاً: ثلاث كلمات مفتاحيّة (`actuator_service_url` · `sahool-actuator` ·
`mqtt.publish(`) داخل `intelligence_governance_gate.py` — تلتقط المسار الأصرح
وحده، وتترك ثلاثة مسارات مفتوحة: موضوع أمر NATS، واستيراد عميل المُشغِّل مباشرةً،
والوصول عبر غلاف/مُرحِّل يُخفي النداء خلف وحدة أخرى.

المسار القانونيّ الوحيد (موثَّق في المصدر نفسه):

    توصية محرّك ─▶ حواجز ─▶ موافقة ─▶ core.decision_dispatch (نقيّ)
      ─▶ core.dispatch_executor (يُدرِج READY فقط) ─▶ core.actuator_command (نقيّ)
      ─▶ actuator-service يستهلك الطابور ويوقّع HMAC ثمّ ينشر الأمر

فالدماغ يُصدِر **مرشّح قرار** يُراجَع، لا أمراً يُنفَّذ.

قاعدتان مختلفتان عمداً — لأنّ الخطر مختلف:

1. **إطلاق الأثر (كشّافان ١+٢) مقيَّد عالميّاً:** أيّ ملفّ إنتاجيّ يحمل نقطة نهاية
   المُشغِّل أو ينشر أمراً على وسيط يجب أن يكون في قائمة سماح **مُعلَّلة سطراً سطراً**
   داخل `docs/architecture/physical_effect_boundary_contract.json`. ملفّ جديد يطلق
   أثراً ⇒ CI يسقط حتى يُسمّى ويُعلَّل — أي adjudication مرئيّ في المراجعة.
2. **البلوغ بالاستيراد (كشّافان ٣+٤) مقيَّد داخل مناطق الدماغ فقط:** استيراد وحدات
   التوزيع سلوك طبيعيّ داخل المنصّة نفسها؛ لكنّه من الدماغ يعني تجاوز حلقة المراجعة
   عبر وسيط. فرضه عالميّاً كان سيولّد ضجيجاً بلا خطر مقابل.

ويُفرَض عكسيّاً كعقد التوافق الدائم (#735): إدخال سماح بلا مطابقة حيّة يُسقِط CI،
كي لا يتراكم إدخال ميّت يُغطّي ملفّاً يُعاد إدخاله لاحقاً بلا مراجعة. وإدخال سماح
داخل منطقة دماغ يُسقِط CI كذلك — فلا يُعالَج خرقٌ مستقبليّ بترخيصه.

الفحص يجري على **الكود المُنفَّذ وحده**: تُجرَّد docstrings والتعليقات عبر AST (النمط
نفسه في `decision_candidate_boundary_gate.py`) مع إبقاء قيم السلاسل — لأنّ التوثيق
يسمّي الممنوع بالنفي مشروعاً («لا يُطلِق MQTT مباشرةً»)، بينما `"sahool/actuator/…"`
كقيمة نداء حقيقيّ يبقى مكشوفاً.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/architecture/physical_effect_boundary_contract.json"

# ملفّات لا تُفحَص: الاختبارات (تبني حالات الخرق عمداً) وأدوات scripts/ (الحرّاس
# أنفسهم يذكرون الرموز كي يفحصوها — حارس يُسقِط حارساً إيجابيّة كاذبة بالبناء).
_SKIP_DIR_PARTS = {"__pycache__", ".venv", "node_modules", "site-packages", ".git"}
_SKIP_TOP = {"scripts", "tests", "tests_v9"}


def _is_test_path(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return name.startswith("test_") or name.endswith("_test.py") or "/tests/" in f"/{rel}"


# ١) نقطة نهاية المُشغِّل عبر HTTP/الخدمة.
_RX_HTTP = re.compile(r"actuator_service_url|sahool-actuator|https?://actuator", re.I)
# ٢) نشر أمر على وسيط (MQTT topic أو NATS subject) — لا الاشتراك ولا القراءة.
_RX_BROKER = re.compile(r"mqtt\.publish\(|sahool/actuator/|sahool\.actuator\.")
EMISSION = {"http_actuator_endpoint": _RX_HTTP, "broker_command_publish": _RX_BROKER}

# ٣) عميل المُشغِّل/باني الأمر، و٤) طبقة الإدراج/الترحيل. تُرصَد بالـAST لا بتعبير
# نمطيّ: `from api import phase_runtime_workers` يضع الاسم المستهدَف **بعد** import،
# فتعبيرٌ يفحص ما بعد `from` وحده يمرّره — وهي ثغرة حقيقيّة كشفها التكذيب.
REACH_MODULES = {
    "actuator_client_import": {"actuator_runtime", "actuator_command"},
    "relay_indirection_import": {"dispatch_executor", "phase_runtime_workers", "decision_dispatch"},
}


def imported_tokens(code: str) -> set[str]:
    """كلّ اسم وحدة يبلغه الملفّ بالاستيراد: أجزاء المسار + الأسماء المستورَدة منه."""
    tokens: set[str] = set()
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return tokens
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                tokens.update(alias.name.split("."))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                tokens.update(node.module.split("."))
            for alias in node.names:
                tokens.add(alias.name)
    return tokens


def reach_categories(code: str) -> set[str]:
    tokens = imported_tokens(code)
    return {name for name, mods in REACH_MODULES.items() if tokens & mods}


def _executable_source(text: str) -> str:
    """الكود المُنفَّذ وحده: تسقط التعليقات مع AST وتُجرَّد docstrings، وتبقى القيم."""
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(getattr(body[0], "value", None), ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def _production_files() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for path in sorted(ROOT.rglob("*.py")):
        parts = set(path.parts)
        if parts & _SKIP_DIR_PARTS:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel.split("/", 1)[0] in _SKIP_TOP or _is_test_path(rel):
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        try:
            code = _executable_source(raw)
        except SyntaxError:
            continue  # ملفّ لا يُحلَّل ليس مسار تنفيذ حيّاً
        out.append((rel, code))
    return out


def scan() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """يُرجِع (إطلاق الأثر, البلوغ بالاستيراد) — كلاهما rel ⇒ مجموعة فئات."""
    emissions: dict[str, set[str]] = {}
    reaches: dict[str, set[str]] = {}
    for rel, code in _production_files():
        for name, rx in EMISSION.items():
            if rx.search(code):
                emissions.setdefault(rel, set()).add(name)
        found = reach_categories(code)
        if found:
            reaches[rel] = found
    return emissions, reaches


def _contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def check() -> list[str]:
    contract = _contract()
    zones: list[str] = [z["path"] for z in contract["forbidden_zones"]]
    allow: dict[str, dict] = {e["path"]: e for e in contract["allowlist"]}
    errors: list[str] = []

    def in_zone(rel: str) -> str | None:
        return next((z for z in zones if rel == z or rel.startswith(z.rstrip("/") + "/")), None)

    # إدخال سماح داخل منطقة دماغ: لا يُعالَج الخرق بترخيصه.
    for rel in sorted(allow):
        zone = in_zone(rel)
        if zone:
            errors.append(
                f"قائمة السماح تحمل ملفّاً داخل منطقة دماغ ({zone}): {rel} — "
                "منطقة الدماغ لا تُرخَّص إطلاقاً؛ أصدِر مرشّح قرار بدل الأمر."
            )

    emissions, reaches = scan()

    for rel in sorted(emissions):
        zone = in_zone(rel)
        cats = ", ".join(sorted(emissions[rel]))
        if zone:
            errors.append(
                f"مسار أثر فيزيائيّ داخل منطقة الدماغ {zone}: {rel} [{cats}] — "
                "المسار القانونيّ: مرشّح قرار ⇒ حواجز ⇒ موافقة ⇒ Decision-Service."
            )
        elif rel not in allow:
            errors.append(
                f"إطلاق أثر فيزيائيّ من ملفّ غير مُدرَج: {rel} [{cats}] — "
                f"أضِف إدخالاً مُعلَّلاً في {CONTRACT.relative_to(ROOT)} أو أزِل المسار."
            )

    for rel in sorted(reaches):
        zone = in_zone(rel)
        if zone:
            cats = ", ".join(sorted(reaches[rel]))
            errors.append(
                f"بلوغ الأثر عبر استيراد من منطقة الدماغ {zone}: {rel} [{cats}] — "
                "الغلاف/المُرحِّل لا يُغيّر الحدّ؛ الدماغ يقترح ولا يُنفّذ."
            )

    # إنفاذ عكسيّ: إدخال سماح بلا مطابقة حيّة (عقد بائت).
    for rel in sorted(set(allow) - set(emissions)):
        errors.append(
            f"إدخال سماح بلا مسار أثر حيّ مطابق: {rel} — "
            "أزِله؛ الإدخال الميّت يُغطّي ملفّاً يُعاد إدخاله لاحقاً بلا مراجعة."
        )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="افحص (الافتراضيّ)")
    parser.add_argument("--list", action="store_true", help="اعرض المسارات المرصودة فقط")
    args = parser.parse_args()

    if args.list:
        emissions, reaches = scan()
        for rel in sorted(emissions):
            print(f"emission {rel}: {sorted(emissions[rel])}")
        for rel in sorted(reaches):
            print(f"reach    {rel}: {sorted(reaches[rel])}")
        return 0

    errors = check()
    if errors:
        print("physical_effect_boundary_guard_failed")
        print("\n".join(f"- {e}" for e in errors))
        return 1
    print("physical_effect_boundary_guard_ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
