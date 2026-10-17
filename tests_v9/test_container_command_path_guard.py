#!/usr/bin/env python3
"""عقد ``container_command_path_guard`` — «مُسجَّل في compose» ليس «موجود في الصورة».

الواقعة المقيسة: ``sahool-canonical-execution-learning-worker`` كان يُنفَّذ من
``/app/scripts/workers/…`` بينما ``services/sahool-platform/Dockerfile`` ينسخ ``shared/``
وجذر الخدمة **فقط**. الحاوية تموت عند الإقلاع، و``restart: unless-stopped`` يُعيدها إلى
الأبد. والاختبار القائم ``test_worker_is_registered_in_compose`` بقي **أخضر طوال الوقت**:
يقرأ نصّ compose ويؤكّد أنّ الاسم والمسار مذكوران — وهما مذكوران.

وهذا الملفّ يُثبّت **الخاصّيّة** لا التنفيذ: أنّ الحارس يفحص، ويرصد، ولا يخضرّ بلا عين.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts/ci/container_command_path_guard.py"
DOCKERFILE = ROOT / "services/sahool-platform/Dockerfile"


@pytest.fixture(scope="module")
def guard():
    spec = importlib.util.spec_from_file_location("_container_command_path_guard", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_committed_tree_is_clean(guard):
    problems, examined = guard.audit()
    assert examined, "لا زوج مفحوص — حارسٌ بلا عين"
    assert problems == [], "\n".join(problems)


def test_it_actually_examines_something(guard):
    """أخضرٌ بصفر أزواج مفحوصة هو الصفر الصامت الذي يوجد هذا الحارس ليمنعه."""
    # أرضيّةُ «≥ 4» صارت أزواجاً مُسمّاة (2026-10-17): أُزيل weather-polygon-worker بقرار
    # مالك (WEATHER-FORECAST-TOPIC-HAS-NO-PUBLISHER-01) فنزل العدد إلى ٣ — والعددُ وحده
    # لا يقول **أيّ** زوج غاب. الأزواجُ المُسمّاة تقول، ومساواتُها بالعدد تمنع زوجاً خفيّاً.
    import yaml

    expected = {
        ("docker-compose.v9.yml", "sahool-weather-signal-engine", "/app/worker_health_probe.py"),
        ("docker-compose.v9.yml", "sahool-telegram-bot", "/app/bot_readiness.py"),
        (
            "docker-compose.v9.yml",
            "sahool-canonical-execution-learning-worker",
            "/app/workers/canonical_execution_learning_worker.py",
        ),
    }
    seen = set()
    for compose in sorted(ROOT.glob("docker-compose*.yml")):
        document = yaml.safe_load(compose.read_text(encoding="utf-8")) or {}
        for name, service in (document.get("services") or {}).items():
            if isinstance(service, dict) and isinstance(service.get("build"), dict):
                seen |= {(compose.name, name, p) for p in guard.executed_paths(service)}
    missing = expected - seen
    assert not missing, f"أزواجٌ مُسمّاة لم تعد تُفحَص — تضييق صامت للنطاق: {sorted(missing)}"
    _, examined = guard.audit()
    assert examined == len(seen) >= len(expected), (
        f"الحارس فحص {examined} والشجرة تُعلِن {len(seen)} — زوجٌ لا يراه أحدهما"
    )


def test_the_worker_now_lives_where_the_image_can_see_it(guard):
    """البرهان على الإصلاح نفسه، مشتقّاً من مجموعة ``COPY`` لا من مسارٍ مكتوب."""
    source = guard.sources_for(
        DOCKERFILE,
        "/app/workers/canonical_execution_learning_worker.py",
        context=ROOT,
    )
    assert source == "services/sahool-platform/workers/canonical_execution_learning_worker.py"


def test_the_old_location_is_still_unreachable_from_that_image(guard):
    """لو أُعيد الملفّ إلى ``scripts/`` لعاد العطل — والحارس يقولها لا التوثيق."""
    assert (
        guard.sources_for(
            DOCKERFILE,
            "/app/scripts/workers/canonical_execution_learning_worker.py",
            context=ROOT,
        )
        is None
    )


def test_copy_semantics_are_applied_not_approximated(guard):
    """التقريب أنتج إيجابيّات كاذبة عند أوّل قياس؛ الحالتان مُثبَّتتان هنا.

    ``COPY dir/ /app/x/`` ينسخ **محتويات** الدليل، و``COPY file /app/file`` ملفّاً إلى
    ملفّ. أوّل نسخة عالجت الأولى وحدها فاتّهمت ثلاث خدمات سليمة تنسخ مسبار صحّتها
    بالصيغة الثانية.
    """
    # محتويات دليل (shared/ ⇒ /app/shared/)
    assert (
        guard.sources_for(DOCKERFILE, "/app/shared/wofost/engine.py", context=ROOT)
        == "shared/wofost/engine.py"
    )
    # ملفّ ⇒ ملفّ، في صورة أخرى
    probe = ROOT / "services/weather-signal-engine/Dockerfile"
    assert (
        guard.sources_for(probe, "/app/worker_health_probe.py", context=ROOT)
        == "services/weather-signal-engine/worker_health_probe.py"
    )


def test_the_build_context_is_honoured_not_the_repository_root(guard):
    """‏``dockerfile`` ومسارات ``COPY`` نسبيّة إلى ``build.context``.

    خلطُ الاثنين أنتج **خمس** اتّهامات كاذبة عند أوّل تشغيل — كلّ خدمة سياقها دليل
    فرعيّ (``./frontend``) بدت وكأنّ Dockerfile الخاصّ بها غير موجود.
    """
    source = TOOL.read_text(encoding="utf-8")
    assert 'build.get("context"' in source
    assert "context=context" in source


def test_a_missing_path_is_reported_with_the_service_that_executes_it(guard, tmp_path):
    """رسالة الحارس جزءٌ منه: من لا تسمّي رسالتُه الخدمةَ والمسار تُرسِل قارئها للملفّ الخطأ."""
    (tmp_path / "Dockerfile").write_text(
        "FROM x\nCOPY only_this.py /app/only_this.py\n", encoding="utf-8"
    )
    (tmp_path / "only_this.py").write_text("", encoding="utf-8")
    (tmp_path / "docker-compose.probe.yml").write_text(
        "services:\n"
        "  ghost:\n"
        "    build:\n"
        "      context: .\n"
        "      dockerfile: Dockerfile\n"
        "    command: [python, /app/absent.py]\n",
        encoding="utf-8",
    )
    problems, examined = guard.audit(root=tmp_path)
    assert examined == 1
    assert len(problems) == 1
    assert "ghost" in problems[0] and "/app/absent.py" in problems[0]


def test_a_path_the_image_does_place_is_not_reported(guard, tmp_path):
    """التكذيب في الاتّجاه الآخر: حارسٌ يتّهم الجميع لا يقيس شيئاً."""
    (tmp_path / "Dockerfile").write_text("FROM x\nCOPY src/ /app/\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src/present.py").write_text("", encoding="utf-8")
    (tmp_path / "docker-compose.probe.yml").write_text(
        "services:\n"
        "  real:\n"
        "    build:\n"
        "      context: .\n"
        "      dockerfile: Dockerfile\n"
        "    command: [python, /app/present.py]\n",
        encoding="utf-8",
    )
    problems, examined = guard.audit(root=tmp_path)
    assert examined == 1
    assert problems == []


def test_dockerignore_excludes_a_file_the_copy_claims_to_place(guard, tmp_path):
    """‏``COPY`` لا يتغلّب على ``.dockerignore`` — والملفّ المستبعَد ليس في الصورة."""
    (tmp_path / "Dockerfile").write_text("FROM x\nCOPY src/ /app/\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src/excluded.py").write_text("", encoding="utf-8")
    (tmp_path / "docker-compose.probe.yml").write_text(
        "services:\n"
        "  ghost:\n"
        "    build:\n"
        "      context: .\n"
        "      dockerfile: Dockerfile\n"
        "    command: [python, /app/excluded.py]\n",
        encoding="utf-8",
    )
    assert guard.audit(root=tmp_path)[0] == [], "بلا .dockerignore يجب أن يمرّ"
    (tmp_path / ".dockerignore").write_text("excluded.py\n", encoding="utf-8")
    problems, _ = guard.audit(root=tmp_path)
    assert len(problems) == 1 and "/app/excluded.py" in problems[0]


def test_an_empty_audit_fails_closed_instead_of_printing_ok(guard, tmp_path, monkeypatch):
    """صفرُ أزواجٍ مفحوصة ليس نجاحاً — وهو الصنف الذي أوقع حارس الدماغ قبلاً."""
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    assert guard.main(["--check"]) == 2
