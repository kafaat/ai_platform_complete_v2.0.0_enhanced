"""تكذيبُ حلقةِ دليل الاعتماد: الإنتاج · العبور · الإعلان.

كلُّ اختبارٍ هنا يقابل تزييفاً بعينه، ويحمرّ إن عُطِّل الحارسُ الذي يقطعه.

**والسياقُ الذي أوجب الملفّ:** `production-certification-blockers.yml` حمل أربعَ
وظائفِ «دليل» لا تكتب دليلاً، وخمسةَ حواجزَ كلُّها `pending`. فالحكمُ `false` كان
يُقرأ عجزاً في القياس بينما سببُه أنّ **لا شيء يُنتِج ما يقرؤه المُحكِّم** — ومثلُ
هذا يُقرأ بمرور الوقت دعوةً إلى تلفيق المُدخَل بدل إصلاح المُنتِج.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EMITTER = ROOT / "scripts" / "ci" / "emit_certification_evidence.py"
PRODUCER_GUARD = ROOT / "scripts" / "ci" / "certification_evidence_producer_guard.py"
CONTRACT = ROOT / "docs" / "architecture" / "certification_evidence_producers.json"
WORKFLOW = ROOT / ".github" / "workflows" / "production-certification-blockers.yml"

#: أصلٌ صالحُ الشكل لعدّاءٍ وهميّ — يُمرَّر **بيئةً** كما في العدّاء الحقيقيّ.
_CI_ENV = {
    "GITHUB_REPOSITORY": "kafaat/ai_platform_complete_v2.0.0_enhanced",
    "GITHUB_WORKFLOW": "Production Certification Blockers",
    "GITHUB_RUN_ID": "1234567890",
    "GITHUB_SHA": "0123456789abcdef0123456789abcdef01234567",
}


def _run(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    # البيئةُ تُبنى من الصفر لا تُورَّث: `GITHUB_*` مُسرَّبةٌ من عدّاء CI نفسِه كانت
    # ستجعل حالةَ «خارج CI» تمرّ في CI وتسقط محلّيّاً — وهو الصنفُ الذي أسقط
    # `test_certification_verdict_is_not_forgeable` سبعَ مرّاتٍ في عدّاءٍ سابق.
    clean = {k: v for k, v in os.environ.items() if not k.startswith("GITHUB_")}
    clean["PYTHONIOENCODING"] = "utf-8"
    if env:
        clean.update(env)
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=clean,
    )


# ═══ ① الباعث: الأصلُ يُورَث ولا يُمرَّر ══════════════════════════════════


@pytest.mark.unit
def test_emitter_refuses_to_write_outside_a_ci_run(tmp_path: Path) -> None:
    """خارج عدّاء Actions لا انبعاث — وإلّا صار الباعثُ أداةَ تلفيقٍ محلّيّة."""
    result = _run([str(EMITTER), "--blocker", "P-CERT-2", "--out", str(tmp_path)])
    assert result.returncode != 0
    assert "GITHUB_REPOSITORY" in result.stderr + result.stdout
    assert not list(tmp_path.glob("*.json"))


@pytest.mark.unit
@pytest.mark.parametrize("field", ["repository", "workflow", "workflow_run_id", "commit"])
def test_emitter_rejects_provenance_passed_as_an_argument(field: str, tmp_path: Path) -> None:
    """تمريرُ حقلِ أصلٍ وسيطاً يُرفَض صراحةً — لا يُتجاهَل بصمت.

    التجاهلُ الصامت أسوأ من القبول: يجعل محاولةَ التلفيق تبدو ناجحة.
    """
    result = _run(
        [str(EMITTER), "--blocker", "P-CERT-2", "--out", str(tmp_path), "--field", f"{field}=x"],
        env=_CI_ENV,
    )
    assert result.returncode != 0
    assert field in result.stderr + result.stdout


@pytest.mark.unit
def test_emitter_rejects_provenance_smuggled_through_a_fields_file(tmp_path: Path) -> None:
    """ولا يُلتَفُّ على الحجز بملفِّ حقول — مصدرُ الحقول لا يغيّر ما هو محجوز."""
    fields = tmp_path / "fields.json"
    fields.write_text(json.dumps({"repository": "attacker/x"}), encoding="utf-8")
    result = _run(
        [
            str(EMITTER),
            "--blocker",
            "P-CERT-2",
            "--out",
            str(tmp_path),
            "--fields-file",
            str(fields),
        ],
        env=_CI_ENV,
    )
    assert result.returncode != 0
    assert "repository" in result.stderr + result.stdout


@pytest.mark.unit
def test_emitter_rejects_an_empty_minimum_field(tmp_path: Path) -> None:
    """قائمةٌ خاويةٌ تُرضي فحصَ **الحضور** — وهي بعينها ثغرةُ الدليل المُلفَّق."""
    result = _run(
        [
            str(EMITTER),
            "--blocker",
            "P-CERT-2",
            "--out",
            str(tmp_path),
            "--field",
            "command=x",
            "--field",
            "index_url_policy=y",
            "--json-field",
            "lock_files=[]",
        ],
        env=_CI_ENV,
    )
    assert result.returncode != 0
    assert "lock_files" in result.stderr + result.stdout


@pytest.mark.unit
def test_emitter_writes_evidence_the_strict_guard_accepts(tmp_path: Path) -> None:
    """المسارُ السعيد يُقاس أيضاً: باعثٌ يرفض كلَّ شيءٍ حارسٌ لا بوّابة."""
    result = _run(
        [
            str(EMITTER),
            "--blocker",
            "P-CERT-2",
            "--out",
            str(tmp_path),
            "--field",
            "command=bash scripts/ci/compile_transitive_service_locks.sh",
            "--field",
            "index_url_policy=pypi",
            "--json-field",
            """lock_files=[{"path": "services/x/requirements.lock"}]""",
        ],
        env=_CI_ENV,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads((tmp_path / "transitive_locks_summary.json").read_text(encoding="utf-8"))
    assert payload["status"] == "verified"
    assert payload["repository"] == _CI_ENV["GITHUB_REPOSITORY"]
    assert payload["commit"] == _CI_ENV["GITHUB_SHA"]


# ═══ ② المسح: لا يُعتَدّ إلّا بما أنتجه هذا العدّاء ═══════════════════════


@pytest.mark.unit
def test_purge_removes_exactly_the_blocker_files(tmp_path: Path) -> None:
    """يمسح قائمةَ الحارس ولا يوسّع أثرَه إلى بقيّة ملفّات المجلَّد.

    ولمَ المسحُ أصلاً: المُحكِّم يستنسخ الشجرة ثمّ يقرأ `certification/evidence/`،
    فملفٌّ `verified` **مودَعٌ بـ`git add`** بقيمِ أصلٍ عامّةٍ يعرفها أيُّ مؤلّف كان
    يمرّ بلا أن تُنتِجه وظيفةٌ واحدة.
    """
    sys.path.insert(0, str(ROOT / "scripts" / "ci"))
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_pack_guard", ROOT / "scripts" / "ci" / "production_evidence_pack_guard.py"
    )
    assert spec and spec.loader
    pack = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pack)

    blocker_files = {item["required_file"] for item in pack.BLOCKERS}
    bystander = "certify_run_deadbeef.json"
    for name in blocker_files | {bystander}:
        (tmp_path / name).write_text("{}", encoding="utf-8")

    result = _run([str(EMITTER), "--purge", "--out", str(tmp_path)], env=_CI_ENV)
    assert result.returncode == 0, result.stderr
    remaining = {p.name for p in tmp_path.glob("*.json")}
    assert remaining == {bystander}


@pytest.mark.unit
def test_verdict_job_purges_before_downloading_artifacts() -> None:
    """المسحُ **قبل** الجلب لا بعده — العكسُ يمحو ما جلبه العدّاء ويُبقي المودَع."""
    import yaml

    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["certification-verdict"]["steps"]
    purge_at = next(i for i, step in enumerate(steps) if "--purge" in str(step.get("run", "")))
    download_at = next(
        i
        for i, step in enumerate(steps)
        if "actions/download-artifact" in str(step.get("uses", ""))
    )
    assert purge_at < download_at, "المسح يجب أن يسبق download-artifact"


@pytest.mark.unit
def test_produced_blockers_upload_and_undeclared_ones_do_not() -> None:
    """إنتاجٌ بلا عبورٍ لا يبلغ المُحكِّم — ورفعٌ بلا إنتاجٍ يمرّر المودَع.

    ولا يُفحَص «هل تنادي الوظيفةُ الباعثَ في `run`»: انبعاثُ `P-CERT-2` داخل
    `compile_transitive_service_locks.sh` الذي تستدعيه — والصيغةُ الساذجة أسقطته.
    المِلاكُ هو **العقد**: كلُّ حاجبٍ `produced` تُرفَع مصنوعتُه، وكلُّ حاجبٍ مُعلَنٍ
    بلا مُنتِجٍ لا تُرفَع له مصنوعة.
    """
    import importlib.util

    import yaml

    spec = importlib.util.spec_from_file_location(
        "_pack_guard", ROOT / "scripts" / "ci" / "production_evidence_pack_guard.py"
    )
    assert spec and spec.loader
    pack = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pack)
    required_file = {item["id"]: item["required_file"] for item in pack.BLOCKERS}

    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    uploaded_paths = {
        str(step.get("with", {}).get("path", ""))
        for job_id, job in workflow["jobs"].items()
        if job_id != "certification-verdict"
        for step in job["steps"]
        if "actions/upload-artifact" in str(step.get("uses", ""))
    }

    declared = json.loads(CONTRACT.read_text(encoding="utf-8"))["producers"]
    for blocker, entry in declared.items():
        expected = f"certification/evidence/{required_file[blocker]}"
        uploaded = expected in uploaded_paths
        if entry["state"] == "produced":
            assert uploaded, f"{blocker}: 'produced' ولا مصنوعةَ ترفع {expected}"
        else:
            assert not uploaded, f"{blocker}: مُعلَنٌ بلا مُنتِجٍ ومع ذلك تُرفَع {expected}"


# ═══ ③ الإعلان: مُنتِجٌ مُسمّى أو غيابٌ بسببه — لا صمت ════════════════════


@pytest.mark.unit
def test_producer_guard_passes_on_the_tree_as_committed() -> None:
    result = _run([str(PRODUCER_GUARD)])
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.unit
def test_every_blocker_is_declared_in_the_producer_contract() -> None:
    """قائمتان تنحرفان هو الصنفُ الذي أسقط `GUARDS` من التقييم أصلاً."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_pack_guard", ROOT / "scripts" / "ci" / "production_evidence_pack_guard.py"
    )
    assert spec and spec.loader
    pack = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pack)

    declared = json.loads(CONTRACT.read_text(encoding="utf-8"))["producers"]
    assert {b["id"] for b in pack.BLOCKERS} == set(declared)


@pytest.mark.unit
def test_declaring_no_honest_producer_while_emitting_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """**الحاجزُ الفعليّ.** بدونه يبقى الإعلانُ نصّاً يُخالِفه العمل.

    يُكذَّب بطفرةٍ: تُضاف خطوةُ انبعاثٍ لحاجبٍ مُعلَنٍ بلا مُنتِج، فيجب أن يحمرّ الحارس
    **بهذا السبب بعينه**.

    ولمَ يُفحَص السببُ لا رمزُ الخروج وحدَه: أوّلُ صيغةٍ من هذا الاختبار ضبطت
    `guard.ROOT = Path("/")` فصارت مساراتُ الحواجز المُنتِجة كلُّها «غيرَ موجودة»،
    فأرجع الحارسُ `1` لسببٍ آخر — و**نجا** تعطيلُ الفحص المقصود من التكذيب.
    اختبارٌ يمرّ على الطفرة ليس تكذيباً؛ التقطه مسحُ الطفرات لا المراجعة.
    """
    workflow_copy = tmp_path / "wf.yml"
    workflow_copy.write_text(
        WORKFLOW.read_text(encoding="utf-8")
        + "\npython scripts/ci/emit_certification_evidence.py --blocker P-CERT-3\n",
        encoding="utf-8",
    )
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    contract["producers"]["P-CERT-3"]["workflow"] = str(workflow_copy)
    mutated = tmp_path / "contract.json"
    mutated.write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")

    # الحارسُ يقرأ ثوابتَ مساراتٍ في وحدته؛ يُبدَّل **العقدُ وحدَه** لا الجذر.
    import importlib.util

    spec = importlib.util.spec_from_file_location("_producer_guard", PRODUCER_GUARD)
    assert spec and spec.loader
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    guard.CONTRACT = mutated
    assert guard.check() == 1
    out = capsys.readouterr().out
    assert "P-CERT-3" in out
    assert "no_honest_producer" in out and "يُبعَث" in out


@pytest.mark.unit
def test_commented_emission_is_not_counted(tmp_path: Path) -> None:
    """ذكرُ الباعث في تعليقٍ كامل أو ذيل أمرٍ ليس انبعاثاً قابلاً للبلوغ."""
    import importlib.util

    source = tmp_path / "comments.yml"
    source.write_text(
        "# python scripts/ci/emit_certification_evidence.py --blocker P-CERT-3\n"
        "run: echo measured # python scripts/ci/emit_certification_evidence.py --blocker P-CERT-4\n",
        encoding="utf-8",
    )
    spec = importlib.util.spec_from_file_location("_producer_guard", PRODUCER_GUARD)
    assert spec and spec.loader
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    assert guard._emitted_blockers(source) == set()


@pytest.mark.unit
def test_declaring_produced_without_any_emission_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """والوجهُ المقابل: `produced` بلا انبعاثٍ على المسار المُعلَن ادّعاءٌ أيضاً.

    وُجِد بمسحِ طفراتٍ لا بمراجعة: تعطيلُ هذا الفحص وحدَه نجا من الجناح كلِّه
    بينما ماتت الطفراتُ الثلاث الأخرى — أي أنّ نصفَ القاعدة كان بلا شاهد.
    """
    workflow_copy = tmp_path / "wf.yml"
    workflow_copy.write_text("name: no emission here\n", encoding="utf-8")
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    contract["producers"]["P-CERT-2"]["workflow"] = str(workflow_copy)
    contract["producers"]["P-CERT-2"]["producer"] = "scripts/ci/preflight.sh"
    mutated = tmp_path / "contract.json"
    mutated.write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")

    import importlib.util

    spec = importlib.util.spec_from_file_location("_producer_guard", PRODUCER_GUARD)
    assert spec and spec.loader
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    guard.CONTRACT = mutated
    assert guard.check() == 1
    out = capsys.readouterr().out
    assert "P-CERT-2" in out and "لا انبعاثَ له" in out


@pytest.mark.unit
def test_a_declared_producer_that_no_longer_exists_is_rejected(tmp_path: Path) -> None:
    """سكربتٌ مُعلَنٌ محذوف **تقلّصُ تغطية** لا خطأُ مسار — يُسمّى باسمه."""
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    contract["producers"]["P-CERT-1"]["producer"] = "scripts/ci/deleted_collector.py"
    mutated = tmp_path / "contract.json"
    mutated.write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")

    import importlib.util

    spec = importlib.util.spec_from_file_location("_producer_guard", PRODUCER_GUARD)
    assert spec and spec.loader
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    guard.CONTRACT = mutated
    assert guard.check() == 1


@pytest.mark.unit
def test_an_empty_reason_is_rejected(tmp_path: Path) -> None:
    """إعلانُ غيابٍ بلا سببٍ صمتٌ بصيغةٍ أخرى — وهو ما بُني العقدُ لمنعه."""
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    contract["producers"]["GUARDS"]["reason"] = []
    mutated = tmp_path / "contract.json"
    mutated.write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")

    import importlib.util

    spec = importlib.util.spec_from_file_location("_producer_guard", PRODUCER_GUARD)
    assert spec and spec.loader
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    guard.CONTRACT = mutated
    assert guard.check() == 1


# ═══ ④ حدُّ الصدق المُعلَن يبقى مُعلَناً ═══════════════════════════════════


@pytest.mark.unit
def test_the_verdict_is_still_false_on_the_committed_tree() -> None:
    """هذا التغييرُ لا يعتمد المنصّة، ولا يدّعي ذلك.

    الاختبارُ يمنع الادّعاءَ المعاكس: لو صار الحكمُ `true` على شجرةٍ مودَعةٍ بلا
    مصنوعاتِ عدّاء، فذلك دليلٌ **مودَعٌ** — أي بعينه ما بُني المسحُ لقطعه.
    """
    result = _run([str(ROOT / "scripts" / "ci" / "production_certification_blockers_status.py")])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["production_certified"] is False


# ═══ ⑤ شاهدُ P-CERT-1: المُعرِّفُ يُحَلّ ولا يُفترَض ═══════════════════════


def _collector():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_collector", ROOT / "scripts" / "ci" / "collect_full_branch_ci_evidence.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.unit
def test_the_runs_url_never_carries_a_path_in_the_workflow_id_slot(monkeypatch) -> None:
    """نقطةُ `/actions/workflows/{id}/runs` تقبل معرّفاً رقميّاً أو اسمَ ملفّ — لا مساراً.

    **مراجعةٌ آليّةٌ أصابت.** والخطرُ ليس `404` بذاته: سقوطُ الجامع كان يُقرأ «لا عدّاءَ
    CI على هذه البصمة»، فيبقى `P-CERT-1` مُعلَّقاً أبداً ويُقرأ ذلك تقصيراً في تشغيل CI
    لا خطأً في سطرٍ — **عطلٌ يتنكّر في زيّ عُطلٍ آخر**.
    """
    mod = _collector()
    calls: list[str] = []

    def fake_api(url: str, token: str) -> dict:
        calls.append(url)
        if "/actions/workflows?" in url:
            return {"workflows": [{"id": 4242, "path": ".github/workflows/ci.yml"}]}
        if "/runs?" in url:
            return {
                "workflow_runs": [
                    {
                        "id": 7,
                        "status": "completed",
                        "conclusion": "success",
                        "head_branch": "main",
                        "head_sha": "a" * 39 + "b",
                        "html_url": "https://example.invalid/7",
                    }
                ]
            }
        return {"jobs": [{"name": "Unit Tests", "conclusion": "success"}]}

    monkeypatch.setattr(mod, "_api", fake_api)
    monkeypatch.setenv("GITHUB_REPOSITORY", "kafaat/x")
    monkeypatch.setenv("GITHUB_SHA", "a" * 39 + "b")
    monkeypatch.setenv("GITHUB_TOKEN", "t")

    fields = mod.collect()
    runs_url = next(u for u in calls if "/runs?" in u)
    assert "/actions/workflows/4242/runs" in runs_url
    # **المقطعُ نفسُه يُفحَص لا الرابطُ كلُّه.** أوّلُ صيغةٍ لهذا التوكيد كانت
    # `".github" not in runs_url` — وسقطت على `api.github.com`، أي على المضيف لا على
    # موضع المعرّف. توكيدٌ يسقط لسببٍ غير خاصّيّته يقول «العطلُ هنا» وهو ليس هنا.
    slot = runs_url.split("/actions/workflows/", 1)[1].split("/", 1)[0]
    assert slot == "4242"
    assert "%2F" not in slot and "." not in slot
    assert fields["ci_run_id"] == "7"


@pytest.mark.unit
def test_an_unresolvable_workflow_is_not_reported_as_a_missing_run(monkeypatch) -> None:
    """التشخيصُ يفرّق: «المُعرِّف لم يُحَلّ» ليس «لا عدّاءَ على هذه البصمة».

    وبدون هذا الفرق يُقرأ خطأٌ في السطر تقصيراً في تشغيل CI — وهو ما يُبقي الحاجبَ
    مُعلَّقاً بلا أن يعرف أحدٌ لماذا.
    """
    mod = _collector()
    monkeypatch.setattr(mod, "_api", lambda url, token: {"workflows": [{"id": 1, "path": "x.yml"}]})
    monkeypatch.setenv("GITHUB_REPOSITORY", "kafaat/x")
    monkeypatch.setenv("GITHUB_SHA", "a" * 39 + "b")
    monkeypatch.setenv("GITHUB_TOKEN", "t")

    with pytest.raises(SystemExit) as excinfo:
        mod.collect()
    message = str(excinfo.value)
    assert "المُعرِّفُ نفسُه لم يُحلَّ" in message
    assert "لا عدّاءَ" not in message.split("وهذا")[0]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status", "conclusion"),
    [("completed", "failure"), ("completed", "cancelled"), ("in_progress", None)],
)
def test_no_witness_is_produced_from_a_run_that_did_not_pass(
    status: str, conclusion: str | None, monkeypatch
) -> None:
    """عدّاءٌ فاشلٌ أو قيدَ التشغيل ⇒ سقوطٌ ⇒ الحاجبُ `pending`. لا اعتمادَ بلا شاهد."""
    mod = _collector()

    def fake_api(url: str, token: str) -> dict:
        if "/actions/workflows?" in url:
            return {"workflows": [{"id": 1, "path": ".github/workflows/ci.yml"}]}
        return {"workflow_runs": [{"id": 9, "status": status, "conclusion": conclusion}]}

    monkeypatch.setattr(mod, "_api", fake_api)
    monkeypatch.setenv("GITHUB_REPOSITORY", "kafaat/x")
    monkeypatch.setenv("GITHUB_SHA", "a" * 39 + "b")
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    with pytest.raises(SystemExit):
        mod.collect()


# ═══ ⑥ العبور يفشل مغلقاً، والتوقيع يُتحقَّق منه ═══════════════════════════


def _digest_checker():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_digests", ROOT / "scripts" / "ci" / "verify_certification_evidence_digests.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.unit
def test_an_evidence_file_with_no_producer_digest_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """حالةُ الاستبدال بعينها: ملفٌّ بلغ المُحكِّمَ ولم تُنتِجه وظيفةٌ في هذا العدّاء.

    `download-artifact` يعرض **تحذيراً** عند اختلاف البصمة ويمضي — فبلا مقارنةٍ
    صريحةٍ يبقى نصفُ ما بُني في `--purge` مُبطَلاً: المسحُ يقول «لا يُعتَدّ إلّا بما
    أنتجه هذا العدّاء»، والجلبُ بلا مقارنةٍ يقول «ما جاء من المخزن أنتجَه» — وليستا
    الحقيقةَ نفسَها.

    **والتشخيصُ يُفحَص لا رمزُ الخروج وحدَه.** أوّلُ صيغةٍ لهذا الاختبار أكّدت `== 1`
    فحسب، **فنجت الطفرةُ** التي تُعطّل هذا الفرع: بصمةٌ خاويةٌ تسقط في فرع
    «الاختلاف» أيضاً فيبقى الحكمُ `1`. والفرعان ليسا واحداً — أحدهما **استبدالٌ**
    (لا مُنتِج) والآخر **تلفٌ** (مُنتِجٌ وبصمةٌ لا تطابق). التقطه مسحُ الطفرات.
    """
    (tmp_path / "ci_summary.json").write_text("{}", encoding="utf-8")
    mod = _digest_checker()
    assert mod.check(tmp_path, env={}) == 1
    out = capsys.readouterr().out
    assert "بلا بصمةٍ من مُنتِج" in out
    assert "تخالف ما سجّله" not in out, "شُخِّص استبدالٌ على أنّه تلفُ بصمة"


@pytest.mark.unit
def test_a_mismatching_digest_is_rejected(tmp_path: Path) -> None:
    mod = _digest_checker()
    path = tmp_path / "ci_summary.json"
    path.write_text("{}", encoding="utf-8")
    env = {mod.env_var_for("P-CERT-1"): "0" * 64}
    assert mod.check(tmp_path, env=env) == 1
    # والمطابِقةُ تمرّ — وإلّا كان حارساً يرفض كلّ شيء لا بوّابة.
    assert mod.check(tmp_path, env={mod.env_var_for("P-CERT-1"): mod.sha256_of(path)}) == 0


@pytest.mark.unit
def test_a_recorded_digest_with_no_file_is_rejected(tmp_path: Path) -> None:
    """رُفِع ثمّ ضاع في العبور — سكوتٌ عنه يُبقي الحاجبَ يبدو غيرَ مُنتَجٍ أصلاً."""
    mod = _digest_checker()
    assert mod.check(tmp_path, env={mod.env_var_for("P-CERT-1"): "0" * 64}) == 1


@pytest.mark.unit
def test_the_digest_channel_is_job_outputs_not_the_artifact() -> None:
    """البصمةُ تعبُر في مخرَجات الوظيفة — بصمةٌ **داخل** المصنوعة شاهدٌ يشهد لنفسه.

    مصنوعةٌ تُستبدَل في المخزن تحمل معها بصمتَها الجديدة؛ ومخرَجاتُ الوظيفة جزءٌ من
    حالة تشغيل الـworkflow ولا تمرّ بذلك المخزن.
    """
    import yaml

    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    verdict = workflow["jobs"]["certification-verdict"]
    step = next(
        s
        for s in verdict["steps"]
        if "verify_certification_evidence_digests" in str(s.get("run", ""))
    )
    for value in (step.get("env") or {}).values():
        assert "needs." in value and ".outputs.digest" in value, (
            f"البصمة لا تأتي من مخرَجات وظيفةٍ سابقة: {value!r}"
        )
    # وكلُّ حاجبٍ `produced` يسجّل بصمته في مخرَجات وظيفته.
    declared = json.loads(CONTRACT.read_text(encoding="utf-8"))["producers"]
    produced = {b for b, e in declared.items() if e["state"] == "produced"}
    carried = {
        var.removeprefix("EVIDENCE_SHA256_").replace("_", "-").replace("P-CERT", "P-CERT")
        for var in (step.get("env") or {})
    }
    assert produced <= carried, f"حواجزُ مُنتَجةٌ بلا بصمةٍ عابرة: {sorted(produced - carried)}"


@pytest.mark.unit
def test_the_digest_gate_runs_before_the_manifest_rebuild() -> None:
    """`--write` يُنشئ نائباتٍ ويُعيد بناء البيان — فلو سبق المقارنةَ لأخفى دخيلاً."""
    import yaml

    steps = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["certification-verdict"][
        "steps"
    ]
    names = [str(s.get("name") or s.get("uses") or "") for s in steps]
    gate = next(
        i
        for i, s in enumerate(steps)
        if "verify_certification_evidence_digests" in str(s.get("run", ""))
    )
    write = next(
        i
        for i, s in enumerate(steps)
        if "production_evidence_pack_guard.py --write" in str(s.get("run", ""))
    )
    download = next(
        i for i, s in enumerate(steps) if "actions/download-artifact" in str(s.get("uses", ""))
    )
    assert download < gate < write, f"ترتيبٌ خاطئ: {names}"


@pytest.mark.unit
def test_the_attestation_is_verified_not_merely_issued() -> None:
    """إصدارُ شهادةٍ ليس التحقّقَ منها.

    بلا تحقّقٍ يبقى ادّعاءُ «هويّةٌ لا يملك المؤلّفُ إصدارَها» **أقوى ممّا يُنفَّذ**:
    تُنتَج الشهادة ولا يُقاس أنّها تُقبَل، ولا تُربَط بـworkflow المُوقِّع ولا
    بالبصمة الهدف.
    """
    import yaml

    steps = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["certification-verdict"][
        "steps"
    ]
    verify = next((s for s in steps if "gh attestation verify" in str(s.get("run", ""))), None)
    assert verify is not None, "تُصدَر الشهادةُ ولا يُتحقَّق منها"
    body = str(verify["run"])
    assert "--signer-workflow" in body, "التحقّق لا يربط الشهادة بـworkflow المُوقِّع"
    assert "--source-digest" in body, "التحقّق لا يربط الشهادة بالبصمة الهدف"

    attest_at = next(i for i, s in enumerate(steps) if "actions/attest@" in str(s.get("uses", "")))
    verify_at = steps.index(verify)
    assert attest_at < verify_at, "التحقّق قبل الإصدار لا معنى له"


@pytest.mark.unit
def test_every_job_that_moves_artifacts_declares_the_actions_scope() -> None:
    """`permissions:` على مستوى الوظيفة يُصفِّر كلَّ نطاقٍ غيرِ مذكور.

    فالغيابُ ليس «الافتراضيّ» بل `none` — وهذا يجعل نقصَ نطاقٍ **عطلاً صامتاً في
    الإعداد** لا خطأً ظاهراً في الكود. وحدَه تشغيلُ الـworkflow يكشفه، وهي
    `workflow_dispatch` فقد تبيت شهوراً.

    مقيسٌ على مراجعةٍ آليّة: `certification-verdict` كان يجلب مصنوعاتٍ بلا
    `actions: read` بينما تُعلِنه وظيفةُ `P-CERT-1` للسبب نفسِه — تعريفان لحاجةٍ
    واحدة، أحدُهما ساقط.
    """
    import yaml

    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for job_id, job in workflow["jobs"].items():
        steps = job.get("steps") or []
        moves = any(
            "actions/download-artifact" in str(s.get("uses", ""))
            or "collect_full_branch_ci_evidence" in str(s.get("run", ""))
            for s in steps
        )
        if not moves:
            continue
        perms = job.get("permissions")
        assert isinstance(perms, dict), f"{job_id}: يجلب من واجهة Actions بلا permissions مُعلَنة"
        assert perms.get("actions") == "read", (
            f"{job_id}: يجلب من واجهة Actions و`actions` = {perms.get('actions')!r}؛ "
            "والنطاقُ غيرُ المذكور في permissions على مستوى الوظيفة يساوي none"
        )
