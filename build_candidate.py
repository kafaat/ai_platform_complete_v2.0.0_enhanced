"""Build and retain a reviewed source candidate; never update its application ref."""
from __future__ import annotations

import ast
import datetime as dt
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from zoneinfo import ZoneInfo

WORK = Path(os.environ.get("GITHUB_WORKSPACE", Path(__file__).parent)).resolve()
TEMP = Path(os.environ.get("RUNNER_TEMP", "/tmp")).resolve()
SOURCE = TEMP / "daily-source"
OUT = TEMP / "daily-build-evidence"
CONFIG = json.loads((WORK / "build-manifest.json").read_text())
CANONICAL = "services/sahool-platform/api/canonical_well_capability.py"
ROUTER = "services/sahool-platform/api/routers/irrigation_mpc.py"
SALINITY_TEST = "services/sahool-platform/tests/test_h5_salinity_ecw_binding.py"
BRIDGE_TEST = "tests_v9/test_lexicographic_mpc_bridge.py"


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(name: str, value: object) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def read_state() -> dict:
    return json.loads((OUT / "build-state.json").read_text())


def git(*args: str, cwd: Path = SOURCE, data: bytes | None = None) -> bytes:
    return subprocess.check_output(["git", *args], cwd=cwd, input=data)


def gt(*args: str, cwd: Path = SOURCE) -> str:
    return git(*args, cwd=cwd).decode().strip()


def run_logged(args: list[str], name: str, cwd: Path = SOURCE) -> dict:
    record = {"argv": args, "started_at_utc": now(), "status": "RUNNING"}
    write_json(name + "-receipt.json", record)
    log_path = OUT / (name + ".log")
    with log_path.open("wb") as log:
        proc = subprocess.Popen(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        require(proc.stdout is not None, "Missing subprocess output")
        for line in iter(proc.stdout.readline, b""):
            log.write(line)
            log.flush()
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()
        code = proc.wait()
    record.update(returncode=code, finished_at_utc=now(), log_sha256=sha256(log_path.read_bytes()),
                  status="PASS" if code == 0 else "FAIL")
    write_json(name + "-receipt.json", record)
    return record


def input_hashes() -> dict[str, str]:
    paths = sorted(set(CONFIG["functional_paths"] + [CANONICAL, SALINITY_TEST, BRIDGE_TEST]))
    return {path: sha256((SOURCE / path).read_bytes()) for path in paths}


def ast_node(text: str, name: str) -> str:
    matches = [n for n in ast.walk(ast.parse(text))
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == name]
    require(len(matches) == 1, f"Ambiguous AST name {name}: {len(matches)}")
    return ast.dump(matches[0], include_attributes=False)


def review_inputs() -> dict:
    checks = []
    ast_pairs = [
        (CANONICAL, "evaluate_water_salinity_gate", CONFIG["main"]),
        (CANONICAL, "evaluate_aquifer_safe_yield_evidence", CONFIG["input_commit"]),
        (CANONICAL, "_number", CONFIG["input_commit"]),
        (CANONICAL, "CanonicalWellCapability", CONFIG["input_commit"]),
        (CANONICAL, "well_capability_to_mpc_constraints", CONFIG["input_commit"]),
        (ROUTER, "_source_canonical_water", CONFIG["input_commit"]),
        (ROUTER, "irrigation_mpc_recommendation", CONFIG["main"]),
        ("services/sahool-platform/api/irrigation_source_binding.py", "aquifer_allocation_blocker", CONFIG["input_commit"]),
    ]
    for path, name, ref in ast_pairs:
        actual = ast_node((SOURCE / path).read_text(), name)
        expected = ast_node(git("show", f"{ref}:{path}").decode(), name)
        require(actual == expected, f"Functional AST differs from reviewed source: {path}::{name}")
        checks.append({"path": path, "symbol": name, "reference": ref, "status": "PASS"})
    exact = {
        "services/sahool-platform/api/irrigation_source_binding.py": CONFIG["input_commit"],
        "services/sahool-platform/tests/test_irrigation_runtime_orchestrator.py": CONFIG["input_commit"],
        "tests_v9/test_h51_field_source_binding_pg.py": CONFIG["input_commit"],
        "docs/architecture/guard_mutation_registry.json": CONFIG["source_parent"],
        "docs/architecture/platform_extraction_map.json": CONFIG["input_commit"],
        SALINITY_TEST: CONFIG["main"],
        BRIDGE_TEST: CONFIG["main"],
    }
    for path, ref in exact.items():
        data = (SOURCE / path).read_bytes()
        require(data == git("show", f"{ref}:{path}"), f"Exact reviewed file differs: {path}")
        checks.append({"path": path, "reference": ref, "sha256": sha256(data), "status": "PASS"})
    fixture = (WORK / CONFIG["reviewed_fixture_file"]).read_bytes()
    require(sha256(fixture) == CONFIG["reviewed_fixture_sha256"], "Reviewed fixture transport mismatch")
    require((SOURCE / "tests_v9/test_canonical_water_state_mpc.py").read_bytes() == fixture, "Combined reviewed fixture differs")
    checks.append({"path": "tests_v9/test_canonical_water_state_mpc.py", "sha256": sha256(fixture),
                   "reference": "Reviewed parent fixture plus scoped current-season graph control", "status": "PASS"})
    gap = (SOURCE / "sahool-brain/gaps/registry.md").read_text()
    section = gap.split("## IRRIGATION-AQUIFER-ALLOCATION-UNVERIFIED-01", 1)
    require(len(section) == 2 and "open" in section[1].split("\n## ", 1)[0], "Aquifer authority gap must remain open")
    return {"status": "PASS", "checks": checks, "production_accepted": False}


def prepare() -> None:
    require(os.environ.get("GITHUB_REF_NAME") == CONFIG["transport_branch"], "Unexpected transport branch")
    OUT.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(WORK / "build-manifest.json", OUT / "build-manifest.json")
    pack = (WORK / "candidates.pack").read_bytes()
    require(sha256(pack) == CONFIG["pack_sha256"], "Input pack SHA256 mismatch")
    git("index-pack", "--stdin", "--fix-thin", "--strict", cwd=WORK, data=pack)
    for commit, tree in ((CONFIG["input_commit"], CONFIG["input_tree"]),
                         (CONFIG["source_parent"], CONFIG["source_parent_tree"]),
                         (CONFIG["main"], CONFIG["main_tree"])):
        require(gt("rev-parse", f"{commit}^{{tree}}", cwd=WORK) == tree, f"Unexpected tree {commit}")
    require(gt("show", "-s", "--format=%P", CONFIG["input_commit"], cwd=WORK) == CONFIG["input_parent"], "Input ancestry mismatch")
    require(not SOURCE.exists(), "Candidate checkout must be fresh")
    git("clone", "--shared", "--no-checkout", str(WORK), str(SOURCE), cwd=WORK)
    git("checkout", "--detach", CONFIG["source_parent"])
    git("remote", "set-url", "origin", f"https://github.com/{CONFIG['repository']}.git")
    git("update-ref", "refs/remotes/origin/main", CONFIG["main"])
    require(gt("rev-parse", "--is-shallow-repository") == "false", "Complete Git history required")
    require(gt("merge-base", CONFIG["main"], "HEAD") == CONFIG["main"], "Parent does not contain pinned main")
    git("config", "user.name", "Codex")
    git("config", "user.email", "codex@openai.com")
    result = run_logged(["git", "cherry-pick", "--no-commit", CONFIG["input_commit"]], "input-application")
    conflicts = gt("diff", "--name-only", "--diff-filter=U").splitlines()
    if result["returncode"] != 0:
        require(bool(conflicts), "Input application failed without merge conflicts")
        unexpected = set(conflicts) - set(CONFIG["generated_paths"]) - set(CONFIG["reviewed_functional_resolution_paths"])
        require(not unexpected, f"Unreviewed functional conflicts: {sorted(unexpected)}")
        for path in conflicts:
            require(gt("rev-parse", f":2:{path}") == gt("rev-parse", f"{CONFIG['source_parent']}:{path}"), f"Unexpected generated seed {path}")
            if path == "tests_v9/test_canonical_water_state_mpc.py":
                fixture = (WORK / CONFIG["reviewed_fixture_file"]).read_bytes()
                require(sha256(fixture) == CONFIG["reviewed_fixture_sha256"], "Reviewed fixture transport mismatch")
                (SOURCE / path).write_bytes(fixture)
            else:
                git("checkout", "--ours", "--", path)
            git("add", "--", path)
    # These two resolutions preserve the concurrently published regression repairs.
    registry = "docs/architecture/guard_mutation_registry.json"
    (SOURCE / registry).write_bytes(git("show", f"{CONFIG['source_parent']}:{registry}"))
    fixture = (WORK / CONFIG["reviewed_fixture_file"]).read_bytes()
    require(sha256(fixture) == CONFIG["reviewed_fixture_sha256"], "Reviewed fixture transport mismatch")
    (SOURCE / "tests_v9/test_canonical_water_state_mpc.py").write_bytes(fixture)
    git("add", "--", registry, "tests_v9/test_canonical_water_state_mpc.py")
    require(not gt("diff", "--name-only", "--diff-filter=U"), "Unresolved conflicts")
    write_json("functional-review.json", review_inputs())
    date = dt.datetime.now(ZoneInfo("Asia/Aden")).date().isoformat()
    note = (
        f"\n\n## {date} — استكمال حارس البئر اليومي فوق رأس #1649 المتزامن\n\n"
        "طُبقت متابعة المصدر المحفوظة `9445616` فوق `b9a3e146` الذي يضم تصحيح الملوحة "
        "`db79cf6` من #1651. يحافظ الدمج على رفض EC غير الصالح وعلى حارس الخزان الجوفي؛ "
        "ويضيف التحقق من رسم القدرة للموسم القانوني عند غياب التعيين أو انتهائه قبل الحل والإرسال. "
        "حُفظ تصحيح مرساة mutation المنشور والتحقق من مدة اليوم في fixture؛ وأضيف شاهد الرسم الموسمي. "
        "اختبارات المصدر المحددة السابقة نجحت في 243 حالة على المدخلات المجمعة قبل انقطاع البيئة. "
        "الفحص المحلي الكامل السابق على 944 لم ينجح: انقطع جامع unit برمز 137، وفشل شاهدان "
        "للتاريخ بسبب غياب التزامات قديمة في النسخة الضحلة. لا يُحوّل ذلك إلى قبول.\n\n"
        "تُعاد الآن المصنوعات بالأمر الرسمي ثم يُثبّت التزام جديد ويُشغّل preflight الافتراضي "
        "الكامل بتاريخه الكامل على عامل مستقل. الأدلة النهائية مرتبطة بالالتزام الذي يقاس وبنتيجة CI؛ "
        "هذا المدخل لا يسبقها بحكم نجاح. تبقى `IRRIGATION-AQUIFER-ALLOCATION-UNVERIFIED-01` "
        "و#1648 مفتوحتين لسلطة التخصيص المستقلة وجدولة المورد المشترك؛ الاحتواء لا يثبت قبولًا ميدانيًا.\n"
    )
    with (SOURCE / "sahool-brain/log.md").open("a") as stream:
        stream.write(note)
    with (SOURCE / "sahool-brain/decisions/ledger.md").open("a") as stream:
        stream.write(
            f"\n\n## {date} — حفظ تحديث الفرع المتزامن وقياس متابعة الحارس على المصدر المجمد\n\n"
            "- **القرار:** تطبيق مدخلات الإصلاح المراجعة فوق `b9a3e146` وإعادة التوليد الرسمي؛ "
            "يُحفظ تصحيح الملوحة من `db79cf6` وتُرفض تعارضات المصدر غير المراجعة.\n"
            "- **سبب القياس:** انقطاع البيئة المحلية وفقدان جزء من تاريخ Git لا يمنحان نجاحًا؛ "
            "يشترط نقل المصدر فحصًا افتراضيًا كاملًا متصلًا بصفر بوابات فاشلة أو متخطاة وثبات الشجرة، "
            "ثم تحديثًا مشروطًا برأس الفرع المقروء وإعادة CI على الرأس المنشور.\n"
            "- **الحدود:** الإصلاح احتواء للمسار اليومي؛ #1648 وسلطة تخصيص الخزان المشتركة تبقيان مفتوحتين. "
            "لا دمج أو نشر إنتاجي أو اعتماد هيدروجيولوجي ضمن هذا القرار.\n"
        )
    hot = SOURCE / "sahool-brain/hot.md"
    hot.write_text(
        f"> {date} — **متابعة #1649 على الرأس المتزامن `b9a3e146`:** حارس البئر اليومي يحفظ "
        "تصحيح الملوحة `db79cf6`؛ التوليد والفحص الكامل على النسخة المجمدة شرطان للرفع. "
        "نجاح الحالات المحددة السابقة لا يعوض الفحص المحلي الذي لم يكتمل بنجاح. "
        "#1648 وفجوة التخصيص المستقل مفتوحتان؛ [السجل](log.md) و[القرار](decisions/ledger.md).\n\n"
        + hot.read_text()
    )
    git("add", "-A")
    git("diff", "--cached", "--check")
    changed = gt("diff", "--cached", "--name-only", CONFIG["source_parent"]).splitlines()
    require(set(changed) <= set(CONFIG["allowed_changed_paths"]), "Unreviewed changed paths before generation")
    write_json("build-state.json", {"status": "PREPARED", "prepared_at_utc": now(),
               "source_parent": CONFIG["source_parent"], "main": CONFIG["main"],
               "input_commit": CONFIG["input_commit"], "resolved_generated_conflicts": conflicts,
               "index_tree_before_generation": gt("write-tree"), "functional_hashes": input_hashes(),
               "production_accepted": False})


def generate() -> None:
    state = read_state()
    require(state["status"] == "PREPARED", "Unexpected generation state")
    require(gt("rev-parse", "HEAD") == CONFIG["source_parent"], "Source parent drift")
    require(gt("write-tree") == state["index_tree_before_generation"], "Staged inputs drift")
    require(input_hashes() == state["functional_hashes"], "Functional inputs changed")
    result = run_logged(["bash", "scripts/ci/regenerate_all_generated.sh"], "generation")
    require(result["returncode"] == 0, "Official generation failed")
    require(input_hashes() == state["functional_hashes"], "Generation changed functional inputs")
    changed = gt("diff", "--name-only", CONFIG["source_parent"]).splitlines()
    require(set(changed) <= set(CONFIG["allowed_changed_paths"]), f"Unexpected generated paths: {sorted(set(changed) - set(CONFIG['allowed_changed_paths']))}")
    require(not gt("ls-files", "--others", "--exclude-standard"), "Unexpected untracked generated outputs")
    git("add", "-A")
    git("diff", "--cached", "--check")
    git("commit", "-m", "Block daily known-well fallback and repair aquifer regression gates")
    require(not gt("status", "--porcelain"), "Candidate worktree is not clean")
    require(gt("show", "-s", "--format=%P", "HEAD") == CONFIG["source_parent"], "Candidate ancestry mismatch")
    write_json("functional-review-final.json", review_inputs())
    state.update(status="BUILT_PENDING_PREFLIGHT", head=gt("rev-parse", "HEAD"), tree=gt("rev-parse", "HEAD^{tree}"),
                 changed_paths=changed, generation=result, built_at_utc=now())
    pack = git("pack-objects", "--stdout", "--revs", "--thin", data=f"{state['head']}\n^{CONFIG['source_parent']}\n".encode())
    (OUT / "candidate-recovery.pack").write_bytes(pack)
    state["candidate_pack_sha256"] = sha256(pack)
    impact_path = OUT / "capability-impact.json"
    impact_result = run_logged(["python", "scripts/ci/pr_capability_impact_gate.py", "--base", CONFIG["main"],
                               "--head", state["head"], "--output", str(impact_path)], "capability-impact-derive")
    require(impact_result["returncode"] in (0, 1) and impact_path.is_file(), "Cannot derive candidate capability impact")
    impact = json.loads(impact_path.read_text())
    require(impact["git"]["merge_base"] == CONFIG["main"] and not impact["declaration"]["errors"], "Invalid impact derivation")
    declaration = ", ".join(impact["direct"]) if impact["direct"] else "none"
    validated = run_logged(["python", "scripts/ci/pr_capability_impact_gate.py", "--base", CONFIG["main"],
                           "--head", state["head"], "--declared", declaration,
                           "--output", str(OUT / "capability-impact-validated.json")], "capability-impact-validation")
    require(validated["returncode"] == 0, "Derived capability declaration failed validation")
    state["capability_impact"] = impact["direct"]
    write_json("build-state.json", state)
    print(json.dumps({"candidate_head": state["head"], "candidate_tree": state["tree"], "status": state["status"]}))


def preflight() -> None:
    state = read_state()
    require(state["status"] == "BUILT_PENDING_PREFLIGHT", "Candidate is not frozen")
    require(gt("rev-parse", "HEAD") == state["head"] and not gt("status", "--porcelain"), "Candidate drift before preflight")
    result = run_logged(["/usr/bin/time", "-v", "-o", str(OUT / "resource-usage.txt"),
                         "bash", "scripts/ci/preflight.sh", "--no-fetch"], "preflight")
    matches = re.findall(r"^═══ إخفاقات: (\d+) · متخطّاة: (\d+) ═══$", (OUT / "preflight.log").read_text(), re.M)
    counts = tuple(map(int, matches[-1])) if matches else None
    status = gt("status", "--porcelain")
    unchanged = gt("rev-parse", "HEAD") == state["head"] and gt("rev-parse", "HEAD^{tree}") == state["tree"] and not status
    inputs_unchanged = input_hashes() == state["functional_hashes"]
    passed = result["returncode"] == 0 and counts == (0, 0) and unchanged and inputs_unchanged
    result.update(status="PASS" if passed else "FAIL", head=state["head"], tree=state["tree"],
                  parent=CONFIG["source_parent"], base=CONFIG["main"], worktree_status=status,
                  source_unchanged=bool(unchanged), functional_inputs_unchanged=inputs_unchanged,
                  gate_failures=counts[0] if counts else None, gate_skips=counts[1] if counts else None,
                  execution_scope="Unchanged contiguous default complete preflight; not --full, not final-head source CI.",
                  skip_scope="Zero skipped gates does not assert zero individual pytest skips.", production_accepted=False)
    write_json("preflight-receipt.json", result)
    state.update(status="PREFLIGHT_PASS_PENDING_RETENTION" if passed else "PREFLIGHT_FAIL", preflight=result)
    write_json("build-state.json", state)
    print(json.dumps(result, ensure_ascii=False))
    require(passed, "Complete default preflight or frozen-source verification failed")


def retain() -> None:
    state = read_state()
    receipt = json.loads((OUT / "preflight-receipt.json").read_text())
    require(state["status"] == "PREFLIGHT_PASS_PENDING_RETENTION", "Unverified source cannot be retained")
    require(receipt["status"] == "PASS" and receipt["returncode"] == 0 and receipt["gate_failures"] == 0 and receipt["gate_skips"] == 0, "Preflight receipt failed")
    require(gt("rev-parse", "HEAD") == state["head"] and not gt("status", "--porcelain"), "Source changed after preflight")
    require(input_hashes() == state["functional_hashes"], "Inputs changed after preflight")
    pack = git("pack-objects", "--stdout", "--revs", "--thin", data=f"{state['head']}\n^{CONFIG['source_parent']}\n".encode())
    git("index-pack", "--stdin", "--fix-thin", "--strict", cwd=WORK, data=pack)
    require(gt("rev-parse", f"{state['head']}^{{tree}}", cwd=WORK) == state["tree"], "Retained tree mismatch")
    patch = git("diff", "--binary", "--full-index", CONFIG["main"], state["head"], "--")
    compressed = gzip.compress(patch, mtime=0)
    paths = gt("diff", "--name-only", CONFIG["main"], state["head"]).splitlines()
    overlay = {"base_commit": CONFIG["main"], "base_tree": CONFIG["main_tree"],
               "source_commit": state["head"], "source_tree": state["tree"],
               "patch_bytes": len(patch), "patch_sha256": sha256(patch),
               "gzip_sha256": sha256(compressed),
               "changed_paths": [{"path": p, "sha256": sha256(git("show", f"{state['head']}:{p}"))} for p in paths]}
    (OUT / "source-overlay.patch.gz").write_bytes(compressed)
    write_json("source-overlay-manifest.json", overlay)
    verified = {"source_commit": state["head"], "source_tree": state["tree"],
                "source_parent": CONFIG["source_parent"], "main": CONFIG["main"],
                "source_branch": CONFIG["source_branch"], "source_ref_updated": False,
                "run_id": os.environ["GITHUB_RUN_ID"], "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
                "generation": state["generation"], "preflight": receipt,
                "capability_impact": state["capability_impact"],
                "functional_hashes": state["functional_hashes"], "retained_at_utc": now(), "production_accepted": False}
    write_json("verified-source.json", verified)
    for name in ("verified-source.json", "build-state.json", "generation-receipt.json", "preflight-receipt.json",
                 "source-overlay.patch.gz", "source-overlay-manifest.json", "functional-review-final.json",
                 "capability-impact.json", "capability-impact-validated.json"):
        shutil.copyfile(OUT / name, WORK / name)
        git("add", "--", name, cwd=WORK)
    git("config", "user.name", "github-actions[bot]", cwd=WORK)
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com", cwd=WORK)
    tree = gt("write-tree", cwd=WORK)
    tip = gt("commit-tree", tree, "-p", os.environ["GITHUB_SHA"], "-p", state["head"],
             "-m", "Retain verified daily guard candidate and evidence [skip ci]", cwd=WORK)
    git("push", "origin", f"{tip}:refs/heads/{CONFIG['transport_branch']}", cwd=WORK)
    print(json.dumps({"retention_commit": tip, "candidate_head": state["head"], "candidate_tree": state["tree"], "source_ref_updated": False}))


if __name__ == "__main__":
    require(len(sys.argv) == 2 and sys.argv[1] in {"prepare", "generate", "preflight", "retain"}, "Expected prepare, generate, preflight, or retain")
    globals()[sys.argv[1]]()
