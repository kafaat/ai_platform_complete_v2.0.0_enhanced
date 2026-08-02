"""منسّق جاهزيّة الإنتاج — الحدّ الصدقيّ وثلاثة عيوب مقيسة أُصلِحت.

الأداة تجمع بوّابات قائمة وتُخرِج حكماً. وقيمتها كلّها في **ما لا تدّعيه**: لا تمسّ
`production_certified` المحكوم، ولا تُعلن `live_ready` بنصف دليل، ولا تُبلِغ صفر
إخفاقات حَرِجة وهي لم تسأل.

العيوب الثلاثة المُصلَحة هنا مقيسة على الصياغة السابقة لا مفترَضة:
  ① `${VAR}` كانت تُرسَل **حرفيّاً** — أُثبِت بالتقاط الترويسة المُرسَلة ومتغيّر
     البيئة مضبوط. الأثر: مسبار «رمز صالح» يحمل رمزاً غير صالح.
  ② `argparse` بـ`action="append"` وافتراضيّ غير `None` **يُوسّع** ولا يستبدل.
  ③ `critical_failures: 0` بينما فحصان حَرِجان تُخُطِّيا.

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_MODULE = _ROOT / "scripts" / "release" / "production_readiness_orchestrator.py"

_spec = importlib.util.spec_from_file_location("production_readiness_orchestrator", _MODULE)
assert _spec and _spec.loader
mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = mod
_spec.loader.exec_module(mod)


def _result(name, category, status, critical=True):
    return mod.Result(name, category, status, critical)


def _runner(tmp_path):
    runner = mod.Runner.__new__(mod.Runner)
    runner.root = tmp_path
    runner.verbose = False
    runner.results = []
    runner.started = 0.0
    runner.commit_sha = "a" * 40
    runner.tree_sha = "b" * 40
    runner._tests_attempted = False
    runner._locale_tests_attempted = False
    runner._repository_tests_attempted = False
    runner._http_probes_attempted = False
    runner._database_probes_attempted = False
    runner._runtime_identity_verified = False
    runner._required_probe_names = set()
    runner._passed_probe_names = set()
    return runner


def _report(tmp_path):
    return json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))


# ── ① توسيع متغيّرات البيئة ────────────────────────────────────────────────────


def test_a_placeholder_is_expanded_from_the_environment(monkeypatch, tmp_path):
    """**العيب الأصليّ:** الترويسة كانت تُرسَل بالنصّ الحرفيّ `${SAHOOL_AGENT_TOKEN}`."""
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "real-token-1")
    assert mod.expand_env("Bearer ${SAHOOL_AGENT_TOKEN}", where="t") == "Bearer real-token-1"


def test_a_missing_variable_fails_instead_of_sending_the_literal(monkeypatch):
    """الصمت أسوأ من الرفض.

    `os.path.expandvars` يُبقي النصّ كما هو عند الغياب — أي يُعيد إنتاج العطل بصمت،
    فيُرسَل رمزٌ غير صالح ويُقرأ 401 على أنّه سلوك مصادقة صحيح.
    """
    monkeypatch.delenv("SAHOOL_TOTALLY_UNSET_TOKEN", raising=False)
    with pytest.raises(mod.ConfigError) as excinfo:
        mod.expand_env("Bearer ${SAHOOL_TOTALLY_UNSET_TOKEN}", where="probe x: header")
    assert "SAHOOL_TOTALLY_UNSET_TOKEN" in str(excinfo.value)


def test_the_probe_path_actually_expands_headers(monkeypatch, tmp_path):
    """الوحدة وحدها لا تكفي: الخاصّيّة تُقاس على المسار الذي يُرسِل فعلاً.

    اختبارٌ يستدعي `expand_env` مباشرةً يبقى أخضر لو نُزِع النداء من
    `live_http_probes` — وهو بالضبط شكل «قدرة موجودة لا تجري» المسجَّل في هذا
    المستودع. فالقياس هنا على الترويسة المُلتقَطة من نداء HTTP.
    """
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "real-token-2")
    captured: dict[str, dict[str, str]] = {}

    def fake_http(url, *, method="GET", timeout=8.0, headers=None, body=None):
        captured[url] = dict(headers or {})
        return 200, b"{}", {}, ""

    monkeypatch.setattr(mod.Runner, "_http", staticmethod(fake_http))

    config = {
        "required_probe_names": ["p"],
        "probes": [
            {
                "name": "p",
                "url": "http://svc:8000/x",
                "headers": {"Authorization": "Bearer ${SAHOOL_AGENT_TOKEN}"},
            }
        ],
    }
    path = tmp_path / "probes.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    runner = _runner(tmp_path)
    runner.live_http_probes(path, "a" * 40)

    sent = captured["http://svc:8000/x"]["Authorization"]
    assert sent == "Bearer real-token-2", sent
    assert "${" not in sent


# ── ② الافتراضيّ التراكميّ ─────────────────────────────────────────────────────


def test_the_rls_table_flag_replaces_the_default_instead_of_extending_it():
    """`action="append"` مع افتراضيّ غير `None` يُوسّع — فلا سبيل إلى التضييق.

    مقيس على الصياغة السابقة: `--required-rls-table audit` أعطى
    `['fields','seasons','users','audit']`.
    """
    parser = __import__("argparse").ArgumentParser()
    parser.add_argument("--required-rls-table", action="append", default=None)

    supplied = parser.parse_args(["--required-rls-table", "audit"]).required_rls_table
    assert tuple(supplied or mod.DEFAULT_REQUIRED_RLS_TABLES) == ("audit",)

    bare = parser.parse_args([]).required_rls_table
    assert tuple(bare or mod.DEFAULT_REQUIRED_RLS_TABLES) == mod.DEFAULT_REQUIRED_RLS_TABLES


# ── ③ المتخطّى الحَرِج يُعَدّ ─────────────────────────────────────────────────────


def test_critical_skips_are_counted_not_hidden_behind_zero_failures(tmp_path):
    """«لم يجد» و«لم ينظر» يجب أن يفترقا في الملخّص.

    الحكم `release_candidate` صحيح حين لا تُطلَب الفحوص الحيّة؛ لكنّ ملخّصاً يقول
    `critical_failures: 0` وحده يُقرأ «لا شيء معلّق».
    """
    runner = _runner(tmp_path)
    runner.results = [
        _result("static", "static", "passed"),
        _result("live_http_probes", "live-http", "skipped", critical=True),
        _result("database_live_contract", "live-db", "skipped", critical=True),
    ]
    code = runner.finalize(
        tmp_path / "report.json",
        require_live=False,
        require_tests=False,
        require_certified=False,
        require_locale_tests=False,
        require_repository_tests=False,
    )
    report = _report(tmp_path)
    assert code == 0
    assert report["verdict"] == "release_candidate"
    assert report["summary"]["critical_failures"] == 0
    assert report["summary"]["critical_skipped"] == 2
    assert report["summary"]["critical_skipped_names"] == [
        "database_live_contract",
        "live_http_probes",
    ]


# ── الحدّ الصدقيّ المحفوظ من الأصل ──────────────────────────────────────────────


def test_certification_is_blocked_without_a_runtime_identity_match(tmp_path):
    """كلّ شيء أخضر، والهويّة غير مربوطة ⇒ محجوب. هذا هو الشرط الذي غاب عن v22."""
    runner = _runner(tmp_path)
    runner.results = [
        _result("source", "source", "passed"),
        _result("static", "static", "passed"),
        _result("unit_suite", "tests", "passed"),
        _result("unit_suite_c_locale", "tests", "passed"),
        _result("http", "live-http", "passed"),
        _result("db", "live-db", "passed"),
        _result("expected_sha_matches_checkout", "source", "passed"),
    ]
    runner._tests_attempted = True
    runner._locale_tests_attempted = True
    runner._repository_tests_attempted = True
    runner._http_probes_attempted = True
    runner._database_probes_attempted = True
    runner._required_probe_names = {"http"}
    runner._passed_probe_names = {"http"}

    code = runner.finalize(
        tmp_path / "report.json",
        require_live=True,
        require_tests=True,
        require_certified=True,
        require_locale_tests=True,
        require_repository_tests=True,
    )
    report = _report(tmp_path)
    assert code == 1
    assert report["verdict"] == "blocked"
    assert report["runtime_sha_bound"] is False


def test_http_alone_is_not_live_ready(tmp_path):
    """نصف الدليل ليس دليلاً: مسابير HTTP بلا فحوص قاعدة البيانات لا تُعطي `live_ready`."""
    runner = _runner(tmp_path)
    runner.results = [_result("static", "static", "passed"), _result("http", "live-http", "passed")]
    runner._http_probes_attempted = True
    runner._required_probe_names = {"http"}
    runner._passed_probe_names = {"http"}

    code = runner.finalize(
        tmp_path / "report.json",
        require_live=True,
        require_tests=False,
        require_certified=False,
        require_locale_tests=False,
        require_repository_tests=False,
    )
    report = _report(tmp_path)
    assert code == 1
    assert report["live_complete"] is False
    assert report["live_ready"] is False


def test_full_evidence_yields_a_candidate_and_never_certifies(tmp_path):
    """**الحدّ الذي لا يُتجاوَز:** أقصى ما تبلغه الأداة «مرشّح».

    `production_certified` ثابت صدق يفرضه CI صفراً حرفيّاً، ورفعه بلا دليل يُفشِل
    البناء. فالأداة تُصدّره `False` مهما اكتمل الدليل.
    """
    runner = _runner(tmp_path)
    runner.results = [
        _result("source", "source", "passed"),
        _result("static", "static", "passed"),
        _result("unit_suite", "tests", "passed"),
        _result("unit_suite_c_locale", "tests", "passed"),
        _result("repository_tests", "repository-tests", "passed"),
        _result("platform_runtime_identity", "live-http", "passed"),
        _result("db", "live-db", "passed"),
        _result("expected_sha_matches_checkout", "source", "passed"),
    ]
    runner._tests_attempted = True
    runner._locale_tests_attempted = True
    runner._repository_tests_attempted = True
    runner._http_probes_attempted = True
    runner._database_probes_attempted = True
    runner._runtime_identity_verified = True
    runner._required_probe_names = {"platform_runtime_identity"}
    runner._passed_probe_names = {"platform_runtime_identity"}

    code = runner.finalize(
        tmp_path / "report.json",
        require_live=True,
        require_tests=True,
        require_certified=True,
        require_locale_tests=True,
        require_repository_tests=True,
    )
    report = _report(tmp_path)
    assert code == 0
    assert report["verdict"] == "production_certified_candidate"
    assert report["production_certified"] is False
    assert "never mutates" in report["truth_boundary"]


# ── ملفّ التهيئة المرافق يُعنوِن ما هو موجود فعلاً ────────────────────────────────


def test_the_example_config_targets_addresses_that_exist(tmp_path):
    """**العيب الرابع:** التهيئة السابقة قصدت `127.0.0.1:8000/:8001`.

    ولا خدمة تنشر منفذاً على المضيف — والفشل يُقرأ «النقطة لا تعمل» وهو يعني «لا أحد
    هنا». يُقاس مقابل compose نفسه لا مقابل ذاكرتي.
    """
    yaml = pytest.importorskip("yaml")
    compose = yaml.safe_load((_ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))
    config = json.loads(
        (_ROOT / "runtime-verification" / "production_readiness_probes.example.json").read_text(
            encoding="utf-8"
        )
    )

    for probe in config["probes"]:
        host = probe["url"].split("://", 1)[1].split("/", 1)[0].split(":")[0]
        assert not host.startswith("127."), (
            f"{probe['name']}: منفذ مضيف — ولا خدمة من الحاملة للهويّة تنشر منفذاً"
        )
        assert host in compose["services"], f"{probe['name']}: مضيف ليس خدمة compose: {host}"
        assert "sahool-internal" in (compose["services"][host].get("networks") or []), (
            f"{probe['name']}: {host} ليس على sahool-internal فلا يُحلّ اسمه من مُشغّل المسابير"
        )


def test_every_required_probe_is_declared_in_the_example_config():
    """قائمة الواجب لا تسمّي مسباراً غير معرَّف — وإلّا حجب العقد بلا سبب مفهوم."""
    config = json.loads(
        (_ROOT / "runtime-verification" / "production_readiness_probes.example.json").read_text(
            encoding="utf-8"
        )
    )
    declared = {p["name"] for p in config["probes"]}
    missing = sorted(set(config["required_probe_names"]) - declared)
    assert not missing, f"مسابير واجبة غير معرَّفة: {missing}"


# ── Repository Tests gate ─────────────────────────────────────────────────────


def test_repository_tests_are_a_separate_critical_job(monkeypatch, tmp_path):
    runner = _runner(tmp_path)
    calls = []

    def fake_command(name, command, **kwargs):
        calls.append((name, command, kwargs["category"], kwargs["critical"]))
        result = _result(name, kwargs["category"], "passed", kwargs["critical"])
        runner.results.append(result)
        return result

    monkeypatch.setattr(runner, "command", fake_command)
    monkeypatch.setattr(
        runner,
        "_repository_pytest_ignores",
        lambda: ["--ignore=tests/integration/test_live_only.py"],
    )
    runner.repository_test_suite(True)

    assert runner._repository_tests_attempted is True
    assert calls[0] == (
        "repository_tests_tree_coverage",
        [sys.executable, "scripts/ci/tests_tree_coverage_guard.py", "--check"],
        "repository-tests",
        True,
    )
    assert calls[1] == (
        "repository_tests",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests",
            "-q",
            "-p",
            "no:cacheprovider",
            "--ignore=tests/integration/test_live_only.py",
        ],
        "repository-tests",
        True,
    )


def test_certification_is_blocked_when_repository_tests_were_not_run(tmp_path):
    runner = _runner(tmp_path)
    runner.results = [
        _result("source", "source", "passed"),
        _result("static", "static", "passed"),
        _result("unit_suite", "tests", "passed"),
        _result("unit_suite_c_locale", "tests", "passed"),
        _result("platform_runtime_identity", "live-http", "passed"),
        _result("db", "live-db", "passed"),
        _result("expected_sha_matches_checkout", "source", "passed"),
    ]
    runner._tests_attempted = True
    runner._locale_tests_attempted = True
    runner._http_probes_attempted = True
    runner._database_probes_attempted = True
    runner._runtime_identity_verified = True
    runner._required_probe_names = {"platform_runtime_identity"}
    runner._passed_probe_names = {"platform_runtime_identity"}

    code = runner.finalize(
        tmp_path / "report.json",
        require_live=True,
        require_tests=True,
        require_certified=True,
        require_locale_tests=True,
        require_repository_tests=True,
    )
    report = _report(tmp_path)
    assert code == 1
    assert report["verdict"] == "blocked"
    assert report["repository_tests_ready"] is False


def test_repository_test_failure_blocks_certification(tmp_path):
    runner = _runner(tmp_path)
    runner.results = [
        _result("source", "source", "passed"),
        _result("static", "static", "passed"),
        _result("unit_suite", "tests", "passed"),
        _result("unit_suite_c_locale", "tests", "passed"),
        _result("repository_tests", "repository-tests", "failed"),
        _result("platform_runtime_identity", "live-http", "passed"),
        _result("db", "live-db", "passed"),
        _result("expected_sha_matches_checkout", "source", "passed"),
    ]
    runner._tests_attempted = True
    runner._locale_tests_attempted = True
    runner._repository_tests_attempted = True
    runner._http_probes_attempted = True
    runner._database_probes_attempted = True
    runner._runtime_identity_verified = True
    runner._required_probe_names = {"platform_runtime_identity"}
    runner._passed_probe_names = {"platform_runtime_identity"}

    code = runner.finalize(
        tmp_path / "report.json",
        require_live=True,
        require_tests=True,
        require_certified=True,
        require_locale_tests=True,
        require_repository_tests=True,
    )
    report = _report(tmp_path)
    assert code == 1
    assert report["repository_tests_ready"] is False


def test_manual_readiness_workflow_exposes_repository_tests_and_enables_it_by_default():
    workflow = (_ROOT / ".github" / "workflows" / "production-readiness-report.yml").read_text(
        encoding="utf-8"
    )
    assert "repository_tests:" in workflow
    assert "default: true" in workflow
    assert "--repository-tests" in workflow


def test_require_certified_executes_repository_tests_not_only_requires_the_verdict():
    source = _MODULE.read_text(encoding="utf-8")
    assert "effective_repository_tests = args.repository_tests or args.require_certified" in source
    assert "runner.repository_test_suite(effective_repository_tests)" in source
    assert "require_repository_tests = True" in source
