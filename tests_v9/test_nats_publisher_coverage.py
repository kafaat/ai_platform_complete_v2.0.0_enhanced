"""حارس تغطية ناشري NATS (H2): كلّ موضوع مُستهلَك له منتِج موثَّق أو waiver.

يفرض عقد ``event_publish_contracts.yaml``: أيّ موضوع NATS يُستهلَك في الكود
(``SUBSCRIPTIONS`` في ``shared/notification_consumers.py`` + أيّ ``.subscribe("literal")``)
يجب أن يظهر في العقد بمنتِجٍ (producer) أو ``reserved_future_subject`` (waiver) —
وإلّا يفشل («مُستهلَك بلا منتِج»). يمنع مناطق أحداث ميّتة دون توثيق، ويُبقي القرار
المعماريّ (ناشرون عبر outbox لا تقليم اشتراكات) مرئيّاً ومُتحقَّقاً في CI.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(_ROOT / "tools"))

import sahool_inspector as si  # noqa: E402


def test_contracts_file_exists():
    assert (_ROOT / "event_publish_contracts.yaml").exists(), "عقد نشر الأحداث مفقود"


def test_every_consumed_subject_has_producer_or_waiver():
    """الحارس العكسيّ يمرّ: لا موضوع مُستهلَك بلا منتِج/waiver."""
    result = si.check_nats_publisher_coverage()
    assert result.status == si.PASS, "موضوعات مُستهلَكة بلا منتِج/waiver:\n" + "\n".join(
        result.findings
    )


def test_notification_subscriptions_are_all_documented():
    """كلّ موضوع في SUBSCRIPTIONS موثَّق في العقد (لا انجراف كود↔عقد)."""
    import yaml

    consumed = set(si._consumed_subjects())
    doc = yaml.safe_load((_ROOT / "event_publish_contracts.yaml").read_text(encoding="utf-8"))
    documented = {e["subject"] for e in doc.get("subjects", []) if e.get("subject")}
    missing = sorted(consumed - documented)
    assert not missing, f"موضوعات مُستهلَكة غير موثَّقة في العقد: {missing}"


def test_guard_is_registered_in_checks():
    """الحارس مُسجَّل في CHECKS فيُشغَّل ضمن المفتّش (بوّابة CI)."""
    assert si.check_nats_publisher_coverage in si.CHECKS


def test_guard_catches_undocumented_consumed_subject(monkeypatch):
    """سلبيّ: موضوع مُستهلَك غير موثَّق ⇒ الحارس يفشل (يثبت أنّه يحرس فعلاً)."""
    orig = si._consumed_subjects
    monkeypatch.setattr(
        si,
        "_consumed_subjects",
        lambda: {**orig(), "sahool.bogus.undocumented": "test:0"},
    )
    result = si.check_nats_publisher_coverage()
    assert result.status == si.FAIL
    assert any("sahool.bogus.undocumented" in f for f in result.findings)


# ── الحارس العكسيّ يقيس ناشراً في الشجرة لا سطراً في العقد ──
# WEATHER-FORECAST-TOPIC-HAS-NO-PUBLISHER-01: ``sahool.weather.forecast.updated`` كان
# مُستهلَكاً (weather-polygon-worker) ومُعفىً في العقد بـ``reserved_future_subject``، فمرّ
# الحارسُ أعلاه — يقيس «موثَّق؟» لا «منشور؟». وكان ``_consumed_subjects`` لا يرى قائمة
# ``SUBSCRIPTIONS`` أصلاً بعد نقلها إلى ``shared/notification_consumers.py``. قرار المالك
# (2026-10-15): إزالة العامل وموضوعه. هذا القسم يقيس الناشر في الشجرة نفسها.

_PUBLISHER_ROOTS = ("services", "agents", "shared")
_SQL_PUBLISHER_ROOT = "migrations"
_PLACEHOLDER = r"[^\s]+"

# موضوعات توجيه وكيل الإشعارات التي لا ناشر لها في الشجرة **بقرار موثَّق**: الأحداث
# الفعليّة تتدفّق عبر ``sahool.events.<type>`` (outbox) والتوجيه الدقيق محجوز. كلٌّ منها
# يجب أن يبقى ``reserved_future_subject`` في العقد (يُتحقَّق أدناه). مساواةُ مجموعات لا
# احتواء: موضوع جديد بلا ناشر يُسقِط الاختبار، وموضوع صار له ناشر يُلزِم حذفه من هنا.
_ROUTING_SUBJECTS_WITHOUT_IN_TREE_PUBLISHER = {
    "sahool.alerts.weather": "تنبيهات الطقس تصل عبر sahool.events.alert.created",
    "sahool.pest.alert": "تنبيهات الآفات عبر sahool.events.alert.created",
    "sahool.irrigation.recommendation": "توصيات الريّ عبر sahool.events.recommendation.created",
    "sahool.fertilizer.recommendation": "توصيات التسميد عبر sahool.events.recommendation.created",
    "sahool.inventory.low_stock": "لا مصدر مخزون بعد؛ يصل عبر sahool.events.* عند بنائه",
    "sahool.task.assigned": "إسناد المهامّ عبر sahool.events.work_order.created",
    "sahool.economic.analysis": "لا مصدر تحليل اقتصاديّ بعد؛ يصل عبر sahool.events.* عند بنائه",
}


def _is_test_path(rel: Path) -> bool:
    return any(part in {"tests", "test", "__pycache__"} for part in rel.parts) or (
        rel.name.startswith("test_") or rel.name == "conftest.py"
    )


def _consumer_side_constants(tree) -> set[int]:
    """معرّفات عُقَد الثوابت التي هي **اشتراك** لا نشر: وسيط ``.subscribe(...)`` الأوّل
    وعناصر ``SUBSCRIPTIONS`` — وإلّا عُدّ الموضوع ناشراً لنفسه."""
    import ast

    ids: set[int] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "subscribe"
            and node.args
        ):
            ids.add(id(node.args[0]))
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "SUBSCRIPTIONS" for t in node.targets
        ):
            ids.update(id(n) for n in ast.walk(node.value))
    return ids


def _template_regex(parts: list[str | None]) -> str | None:
    """قالب موضوع (حرفيّ/None للعنصر المُنسَّق) ⇒ تعبير مطابقة كاملة. قالب يبدأ عنصره
    المُنسَّق قبل مقطعين حرفيّين (``f"sahool.{x}"``) لا يُسمّي نطاقاً فلا يُعدّ ناشراً لأيّ
    موضوع بعينه — وإلّا صار مُرسِل الاختبار في وكيل الإشعارات ناشراً لكلّ شيء."""
    import re

    lead = ""
    for part in parts:
        if part is None:
            break
        lead += part
    if not lead.startswith("sahool.") or lead.count(".") < 2:
        return None
    return "".join(_PLACEHOLDER if p is None else re.escape(p) for p in parts)


def _publisher_templates() -> list[tuple[str, str]]:
    """كلّ قالب موضوع ``sahool.*`` في مصدر غير اختباريّ قد يُنتِج موضوعاً: ثوابت وf-strings
    بايثون (عدا جهة الاشتراك) + ``'sahool.x.' || expr`` في SQL الترحيلات (outbox)."""
    import ast
    import re

    out: list[tuple[str, str]] = []
    for root in _PUBLISHER_ROOTS:
        for py in sorted((_ROOT / root).rglob("*.py")):
            rel = py.relative_to(_ROOT)
            if _is_test_path(rel):
                continue
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            skip = _consumer_side_constants(tree)
            inside_fstring = {
                id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for v in n.values
            }
            for node in ast.walk(tree):
                if id(node) in skip or id(node) in inside_fstring:
                    continue
                parts: list[str | None] | None = None
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    parts = [node.value]
                elif isinstance(node, ast.JoinedStr):
                    parts = [v.value if isinstance(v, ast.Constant) else None for v in node.values]
                if not parts:
                    continue
                rx = _template_regex(parts)
                if rx:
                    out.append((rx, f"{rel.as_posix()}:{node.lineno}"))
    sql_re = re.compile(r"'(sahool\.[A-Za-z0-9_.]+)'\s*\|\|")
    for sql in sorted((_ROOT / _SQL_PUBLISHER_ROOT).rglob("*.sql")):
        text = sql.read_text(encoding="utf-8", errors="replace")
        for m in sql_re.finditer(text):
            rx = _template_regex([m.group(1), None])
            if rx:
                line = text.count("\n", 0, m.start()) + 1
                out.append((rx, f"{sql.relative_to(_ROOT).as_posix()}:{line}"))
    return out


def _probe(subject: str) -> str:
    """مثال ملموس لنمط اشتراك NATS (``*`` رمز واحد، ``>`` رمزان)."""
    return ".".join({"*": "x1", ">": "x2.y2"}.get(tok, tok) for tok in subject.split("."))


def _unpublished_consumed_subjects() -> dict[str, str]:
    import re

    templates = _publisher_templates()
    missing: dict[str, str] = {}
    for subj, loc in sorted(si._consumed_subjects().items()):
        probe = _probe(subj)
        if not any(re.fullmatch(rx, probe) for rx, _ in templates):
            missing[subj] = loc
    return missing


def test_consumed_subjects_include_the_shared_subscription_list():
    """القائمة المشتركة تُقرأ: بلاها لا يقيس الحارسُ العكسيّ شيئاً من وكيل الإشعارات."""
    import ast

    tree = ast.parse((_ROOT / "shared" / "notification_consumers.py").read_text(encoding="utf-8"))
    declared = {
        elt.elts[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "SUBSCRIPTIONS" for t in node.targets)
        for elt in node.value.elts
    }
    assert declared, "SUBSCRIPTIONS فارغة أو غائبة في shared/notification_consumers.py"
    consumed = si._consumed_subjects()
    missing = sorted(declared - set(consumed))
    assert not missing, f"موضوعات SUBSCRIPTIONS لا يراها _consumed_subjects: {missing}"


def test_every_consumed_subject_has_a_publisher_in_the_tree():
    """كلّ موضوع مُستهلَك له قالب ناشر في الشجرة، إلّا موضوعات التوجيه المحجوزة بالاسم."""
    unpublished = _unpublished_consumed_subjects()
    assert set(unpublished) == set(_ROUTING_SUBJECTS_WITHOUT_IN_TREE_PUBLISHER), (
        "مُستهلَك بلا ناشر في الشجرة خارج القائمة المحجوزة: "
        f"{sorted(set(unpublished) - set(_ROUTING_SUBJECTS_WITHOUT_IN_TREE_PUBLISHER))} ؛ "
        "ومحجوز صار له ناشر (احذفه من القائمة): "
        f"{sorted(set(_ROUTING_SUBJECTS_WITHOUT_IN_TREE_PUBLISHER) - set(unpublished))} ؛ "
        f"المواضع: {unpublished}"
    )


def test_routing_subjects_without_publisher_stay_reserved_in_the_contract():
    """الإعفاء بالاسم ليس صمتاً: كلّ موضوع فيه محجوز صراحةً في العقد بسبب."""
    import yaml

    doc = yaml.safe_load((_ROOT / "event_publish_contracts.yaml").read_text(encoding="utf-8"))
    by_subject = {e["subject"]: e for e in doc.get("subjects") or [] if e.get("subject")}
    for subj in _ROUTING_SUBJECTS_WITHOUT_IN_TREE_PUBLISHER:
        entry = by_subject.get(subj) or {}
        assert entry.get("reserved_future_subject") and entry.get("reason"), (
            f"`{subj}` بلا ناشر في الشجرة ويجب أن يكون reserved_future_subject بسبب في العقد"
        )


def test_publisher_index_finds_both_real_producers():
    """الفهرس ليس أعمى: يجد ناشرَي الموضوعَين المنشورَين فعلاً (f-string وSQL outbox)."""
    import re

    templates = _publisher_templates()
    for subj in ("sahool.tenant.*.satellite.*.computed", "sahool.events.>"):
        assert any(re.fullmatch(rx, _probe(subj)) for rx, _ in templates), (
            f"الفهرس لا يجد ناشراً لـ`{subj}` رغم وجوده — الفهرس معطوب"
        )


def test_removed_weather_polygon_worker_left_no_subscriber_behind():
    """قرار المالك (2026-10-15): العامل وموضوعاه أُزيلا كاملاً — لا مشترِك ولا عقد يتيم."""
    import yaml

    assert not (_ROOT / "services" / "weather-polygon-worker").exists(), (
        "weather-polygon-worker أُزيل بقرار مالك؛ عودته تُعيد اشتراكاً بلا ناشر"
    )
    gone = {"sahool.weather.forecast.updated", "sahool.weather.field.overlay.completed"}
    assert not gone & set(si._consumed_subjects()), (
        "موضوع العامل المُزال ما زال مُستهلَكاً في الشجرة — اشتراك بلا ناشر"
    )
    doc = yaml.safe_load((_ROOT / "event_publish_contracts.yaml").read_text(encoding="utf-8"))
    listed = {
        e.get("subject")
        for key in ("subjects", "published_no_consumer")
        for e in doc.get(key) or []
        if isinstance(e, dict)
    }
    assert not gone & listed, "عقد الأحداث ما زال يُعفي موضوعاً لعامل لم يعد موجوداً"
    compose = (_ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8")
    assert "weather-polygon-worker" not in compose, (
        "docker-compose.v9.yml ما زال يُعرّف خدمة العامل المُزال"
    )


def test_nats_subjects_passes_on_the_tree():
    """فحص NATS subjects يمرّ (PASS) على الشجرة الحاليّة."""
    result = si.check_nats_subjects()
    assert result.status == si.PASS, "فحص NATS subjects ليس PASS:\n" + "\n".join(result.findings)


def test_subjects_check_warns_on_unwaived_orphan_and_waiver_silences_it(monkeypatch, tmp_path):
    """سلبيّ على شجرة اصطناعيّة: منشور بلا مشترِك ⇒ WARN، والـwaiver هو ما يُسكِته.
    (كان يُثبَت على overlay.completed الذي أُزيل مع عامله.)"""
    orphan = "sahool.synthetic.orphan.completed"
    svc = tmp_path / "services" / "synthetic"
    svc.mkdir(parents=True)
    (svc / "main.py").write_text(f'await js.publish("{orphan}", b"")\n', encoding="utf-8")
    monkeypatch.setattr(si, "SERVICES", tmp_path / "services")
    monkeypatch.setattr(si, "REPO", tmp_path)
    monkeypatch.setattr(si, "_published_no_consumer_waivers", set)
    result = si.check_nats_subjects()
    assert result.status == si.WARN
    assert any(orphan in f and "منشور بلا مشترِك" in f for f in result.findings)
    monkeypatch.setattr(si, "_published_no_consumer_waivers", lambda: {orphan})
    assert si.check_nats_subjects().status == si.PASS


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
