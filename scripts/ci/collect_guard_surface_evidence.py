#!/usr/bin/env python3
"""شاهدُ `GUARDS`: أيُّ حارسٍ حاجبٍ **شُغِّل فعلاً** على هذه البصمة — والفارقُ لا العدد.

`PRODUCTION-CERTIFICATION-VERDICT-IS-FORGEABLE-AND-UNREACHABLE-01`.

## العطل

`production_evidence_pack_guard.BLOCKERS` يحمل حاجباً غيرَ قابلٍ للإعفاء اسمُه
`GUARDS`، يشترط `certification/evidence/guard_results_summary.json` بحالة `verified`.
و**لا شيءَ في المستودع كلِّه يكتب ذلك الملفّ**: البحثُ عن اسمه يُرجِع قارئَين
وتوثيقاً ولا مُنتِجاً واحداً، ولا وظيفةَ له في `production-certification-blockers.yml`
أصلاً — أربعُ وظائفَ لخمسة حواجز. فالحكمُ `production_certified=false` لم يكن نتيجةَ
قياسٍ فشل، بل نتيجةَ **قياسٍ لا وجودَ له**؛ وبوّابةٌ لا تُغلَق بعملٍ صحيح تُقرأ بمرور
الوقت دعوةً إلى تزييفِ مُدخَلها بدل إصلاح مُنتِجه.

## ولمَ ليس «عُدَّ الحرّاسَ التي مرّت»

`docs/architecture/certification_evidence_producers.json` يصف الإغلاقَ الصحيحَ حرفيّاً
ويرفض البديلَ السهل: أقربُ شاهدٍ متاحٍ (`preflight.sh`) يقيس أقلّيّةَ البوّابات، وختمُ
`verified` فوق أقلّيّةٍ **ادّعاءُ اكتمالٍ من شاهد حضور** — وهو الصنفُ الذي بُنيت حزمةُ
الأدلّة كلُّها لمنعه. فالمطلوب: «مُنتِجٌ يقارن البوّاباتِ المُشغَّلة فعلاً … بقائمة
الحاجبات في كتالوج الحرّاس، فيُخرِج **الفارقَ** لا العدد».

وهذا ما يفعله هذا الملفّ، وأوسعَ ممّا وُصِف: القائمةُ تُشتقّ من `guard_catalogue`
(مصدرُ العدد الوحيد بحسب `CLAUDE.md`)، والقياسُ يشمل **كلَّ** workflow يستدعي حارساً
حاجباً لا `ci.yml` وحدَها — لأنّ مئةً وأربعةَ عشرَ حارساً من مئتين وواحدٍ وسبعين تحجب
خارجَها، وقصرُ الشاهد على `ci.yml` كان سيُنتِج `verified` عن ثمانٍ وخمسين بالمئة: نفسُ
ادّعاءِ الاكتمال بحجمٍ أكبر.

## ماذا يعني «شُغِّل» هنا — بدقّة

لكلّ موضع استدعاء (`workflow` · `job` · `step`) يُسأل عدّاءُ ذلك الـworkflow على
`GITHUB_SHA` نفسِها: هل بلغت **الخطوةُ** بعينها خُلاصةَ `success`؟ ولا يُقبَل غيرُها:

* لا عدّاءَ لذلك الـworkflow على هذه البصمة ⇒ `workflow_not_run_on_this_commit`.
  (وهذا ليس افتراضاً نظريّاً: ثلاثةُ workflows في هذه الشجرة `workflow_dispatch` فقط،
  فحرّاسُها لا تُشغَّل على دفعٍ ولا على PR — حقيقةٌ يُخرِجها الفارقُ ولا يُخفيها عدد.)
* الوظيفةُ غائبةٌ من العدّاء ⇒ `job_missing`؛ خُلاصتُها ليست `success` ⇒ `job_<الخُلاصة>`.
* الخطوةُ غائبةٌ بالاسم ⇒ `step_missing` (إعادةُ تسميةٍ تُسقِط الشاهدَ ولا تُمرّره).
* خُلاصةُ الخطوة ليست `success` — و`skipped` منها — ⇒ `step_<الخُلاصة>`.
  «لم يُقَس» لا يُقرأ «مرّ»؛ وهو الشرطُ نفسُه الذي يُعلِنه `_ACCEPTED_CONCLUSION` في
  `collect_full_branch_ci_evidence`.
* خطوةٌ بـ`continue-on-error` ⇒ `non_blocking_by_declaration` **وإن نجحت**: حارسٌ لا
  يُسقِط الوظيفةَ حين يفشل ليس حاجباً، وعدُّه حاجباً يضخّم سطحَ الحراسة كذباً.

ووظيفةُ **مصفوفة** تُطالَب بكلّ أرجلها: تفريعةٌ واحدةٌ ناجحةٌ من خمسٍ ليست تشغيلاً
للحارس، وأسماءُ الأرجل تُشتقّ من `strategy.matrix.include` بياناتٍ لا تخميناً.

وحارسٌ له مواضعُ عدّة يُعَدّ مُشغَّلاً إن أثبت **أحدُها** — التشغيلُ واقعةٌ لا إجماع.

## حدُّ صدقٍ مُعلَن — ما لا يُثبِته هذا الشاهد

يُثبِت أنّ خطوةً تستدعي الحارسَ انتهت `success` بحسب واجهة GitHub على هذه البصمة. ولا
يُثبِت أنّ الحارسَ **يمسك عطلَه** — تلك خاصّيّةُ مواصفات الطفرة في
`guard_mutation_registry.json`، ويقولها الكتالوجُ نفسُه بعددٍ صريح. ولا يجرد إلّا ما
يُستدعى بنمط `python scripts/ci/<x>.py`؛ حارسٌ يُستدعى عبر `pytest` أو `bash` لا يظهر
هنا — نفسُ حدّ صدقِ الكتالوج، مذكورٌ لأنّ الشاهدَ يرث نطاقَ مصدره.

يعمل بلا pytest — نفس نمط `platform_route_placement_guard`.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import urllib.parse
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
_CATALOGUE = ROOT / "scripts" / "ci" / "guard_catalogue.py"
_CI_WITNESS = ROOT / "scripts" / "ci" / "collect_full_branch_ci_evidence.py"

#: الخُلاصةُ الوحيدةُ المقبولة — نفسُ تعريف `collect_full_branch_ci_evidence`.
ACCEPTED_CONCLUSION = "success"

#: أرضيّةُ جردٍ صريحة. مجلَّدُ workflows غائبٌ أو نمطُ الاستدعاء تغيّر ⇒ صفرُ حرّاس ⇒
#: صفرُ فارق ⇒ `verified` عن **لا شيء**. وهو أخطرُ فشلٍ ممكنٍ في شاهدٍ يُختَم به
#: اعتمادُ إنتاج: «لم يُقَس» يلبس ثوبَ «تامّ». الرقمُ أدنى بكثيرٍ من المرصود (٢٧١)
#: فلا يتحرّك مع كلّ إضافة، ويحمرّ فوراً إن انهار الجرد.
MINIMUM_DISCOVERED_GUARDS = 200

#: الـworkflow الذي يحمل هذا الشاهدَ نفسَه. مواضعُه **لا تُطالَب** — والسببُ دورٌ لا
#: تساهُل: عدّاؤه الجاري لا خُلاصةَ لخطواته بعد (يُرفَض أصلاً لأنّه غيرُ مكتمل)، وعدّاءٌ
#: سابقٌ على البصمة نفسِها لا تكون وظيفةُ الحكم فيه قد نجحت إلّا إن كان هذا الشاهد قد
#: صدر — أي أنّ الشرطَ يشترط نفسَه فلا يتقارب أبداً. وبوّابةٌ لا تُغلَق بعملٍ صحيح هي
#: بعينها العطلُ الذي يُغلقه هذا الملفّ، فلا يجوز أن يُعيد إنتاجه.
#:
#: والاستثناءُ **يُنشَر في الدليل** (`self_witnessing_excluded`) ويُثبَّت أعضاؤه باختبار،
#: كي لا يصير باباً يُنقَل إليه حارسٌ ليُعفى: توسيعُه فعلٌ مقصودٌ يُراجَع، لا انزلاق.
SELF_WITNESSING_WORKFLOW = "production-certification-blockers.yml"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:  # pragma: no cover - بيئةٌ مكسورة
        raise SystemExit(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ═══ الحكمُ — دالّةٌ صافية تُقاس بلا شبكة ═══════════════════════════════════


def _match_job(run: dict, job_name: str) -> list[dict]:
    return [j for j in run.get("jobs", []) if str(j.get("name") or "") == job_name]


def _match_step(job: dict, site: dict) -> dict | None:
    """الخطوةُ المُطابِقة لموضع الاستدعاء، أو `None`.

    الخطوةُ المُسمّاة تُطابَق باسمها حرفاً بحرف. والخطوةُ **بلا اسم** تصل الواجهةَ
    باسمٍ تولّده GitHub من أمرها، وشكلُه التامّ ليس عقداً موثَّقاً أعتمد عليه — فتُطابَق
    باحتواء الاسم لمسار الحارس، وهو صحيحٌ تحت كلّ قراءةٍ معقولةٍ لذلك التوليد. وإن لم
    يُطابِق شيءٌ فالجوابُ `None` ⇒ `step_missing` ⇒ سقوط: لا يُستدَلّ بنجاح الوظيفة على
    خطوةٍ لم تُرَ.
    """
    steps = [s for s in job.get("steps", []) if isinstance(s, dict)]
    declared = site.get("step_name")
    if declared:
        for step in steps:
            if str(step.get("name") or "") == declared:
                return step
        return None
    for step in steps:
        name = str(step.get("name") or "")
        if any(guard in name for guard in site["guards"]):
            return step
    return None


def judge_site(site: dict, runs: dict[str, dict]) -> dict:
    """حكمٌ واحدٌ على موضع استدعاءٍ واحد: `ran`، أو سببٌ مُسمّى لعدم إثباته."""
    verdict: dict[str, object] = {
        "workflow": site["workflow"],
        "job": site["job"],
        "step_name": site["step_name"],
    }
    if site["workflow"] == SELF_WITNESSING_WORKFLOW:
        return {**verdict, "status": "self_witnessing_excluded"}
    if site["continue_on_error"]:
        # وإن نجح: `continue-on-error` تعني أنّ فشلَه لا يُسقِط شيئاً.
        return {**verdict, "status": "non_blocking_by_declaration"}
    if not site["job_names"]:
        return {**verdict, "status": "job_name_not_derivable"}

    run = runs.get(site["workflow"])
    if not run or run.get("error"):
        return {
            **verdict,
            "status": "workflow_not_run_on_this_commit",
            "detail": (run or {}).get("error", "لا عدّاء"),
        }
    verdict["run_id"] = run.get("run_id")

    for job_name in site["job_names"]:
        jobs = _match_job(run, job_name)
        if not jobs:
            return {**verdict, "status": "job_missing", "detail": job_name}
        for job in jobs:
            conclusion = str(job.get("conclusion") or "unknown")
            if conclusion != ACCEPTED_CONCLUSION:
                return {**verdict, "status": f"job_{conclusion}", "detail": job_name}
            step = _match_step(job, site)
            if step is None:
                return {**verdict, "status": "step_missing", "detail": job_name}
            step_conclusion = str(step.get("conclusion") or "unknown")
            if step_conclusion != ACCEPTED_CONCLUSION:
                return {**verdict, "status": f"step_{step_conclusion}", "detail": job_name}
    return {**verdict, "status": "ran"}


def evaluate(sites: list[dict], runs: dict[str, dict]) -> dict:
    """الفارقُ بين ما يُعلِنه الكتالوجُ حاجباً وما أثبتت الواجهةُ تشغيلَه."""
    per_guard: dict[str, list[dict]] = {}
    for site in sites:
        judged = judge_site(site, runs)
        for guard in site["guards"]:
            per_guard.setdefault(guard, []).append(judged)

    guards: list[dict] = []
    unproven: list[dict] = []
    excluded: list[str] = []
    for guard in sorted(per_guard):
        sites_judged = per_guard[guard]
        ran = [s for s in sites_judged if s["status"] == "ran"]
        if not ran and all(s["status"] == "self_witnessing_excluded" for s in sites_judged):
            # يُستدعى في الـworkflow الحامل لهذا الشاهد **وحدَه** ⇒ دورٌ لا يتقارب.
            guards.append({"guard": guard, "status": "self_witnessing_excluded"})
            excluded.append(guard)
            continue
        if ran:
            guards.append(
                {
                    "guard": guard,
                    "status": "ran",
                    "proven_by": [
                        f"{s['workflow']} → {s['job']}"
                        + (f" → {s['step_name']}" if s["step_name"] else "")
                        for s in ran
                    ],
                }
            )
            continue
        reasons = sorted({str(s["status"]) for s in sites_judged})
        guards.append({"guard": guard, "status": "not_proven", "reasons": reasons})
        unproven.append({"guard": guard, "reasons": reasons, "sites": sites_judged})

    return {
        "guards": guards,
        "guards_declared": len(per_guard),
        "guards_proven_run": len(per_guard) - len(unproven) - len(excluded),
        "guards_unproven": unproven,
        "self_witnessing_excluded": excluded,
        "workflows_measured": sorted(runs),
    }


# ═══ الطبقةُ الشبكيّة ═══════════════════════════════════════════════════════


def fetch_runs(workflows: list[str], *, api: str, repository: str, head_sha: str, token: str):
    """لكلّ workflow: أحدثُ عدّاءٍ **مكتمل** على هذه البصمة، بوظائفه وخطواتها."""
    witness = _load(_CI_WITNESS, "_collect_full_branch_ci_evidence")
    index = witness.workflow_index(api, repository, token)
    runs: dict[str, dict] = {}
    for path in workflows:
        workflow_id = index.get(path)
        if workflow_id is None:
            runs[path] = {"error": f"لا workflow مسارُه {path} في {repository}"}
            continue
        listed = witness._api(
            f"{api}/repos/{repository}/actions/workflows/{workflow_id}/runs"
            f"?head_sha={urllib.parse.quote(head_sha)}&per_page=20",
            token,
        ).get("workflow_runs", [])
        completed = [r for r in listed if r.get("status") == "completed"]
        if not completed:
            runs[path] = {
                "error": (
                    f"{len(listed)} عدّاءً على {head_sha[:8]}… ولا مكتمل"
                    if listed
                    else f"لا عدّاءَ على {head_sha[:8]}…"
                )
            }
            continue
        run = completed[0]
        jobs = witness._api(
            f"{api}/repos/{repository}/actions/runs/{run['id']}/jobs?per_page=100", token
        ).get("jobs", [])
        runs[path] = {
            "run_id": str(run.get("id")),
            "run_url": run.get("html_url"),
            "conclusion": str(run.get("conclusion") or ""),
            "jobs": [
                {
                    "name": job.get("name"),
                    "conclusion": job.get("conclusion"),
                    "steps": [
                        {"name": s.get("name"), "conclusion": s.get("conclusion")}
                        for s in (job.get("steps") or [])
                    ],
                }
                for job in jobs
            ],
        }
    return runs


def collect() -> dict:
    catalogue = _load(_CATALOGUE, "_guard_catalogue")
    sites = catalogue.discover_invocation_sites()
    declared = {g for site in sites for g in site["guards"]}
    if len(declared) < MINIMUM_DISCOVERED_GUARDS:
        raise SystemExit(
            f"جردُ الحرّاس {len(declared)} < الأرضيّة {MINIMUM_DISCOVERED_GUARDS} — "
            "لم تُقرأ الشجرة. شاهدٌ عن لا شيء ليس شاهداً على التمام."
        )

    repository = _require_env("GITHUB_REPOSITORY")
    head_sha = _require_env("GITHUB_SHA")
    token = str(os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    if not token:
        raise SystemExit("لا رمزَ وصول (GITHUB_TOKEN) — امنح الوظيفة `permissions: actions: read`.")
    api = str(os.environ.get("GITHUB_API_URL") or "https://api.github.com").rstrip("/")

    workflows = sorted({f".github/workflows/{site['workflow']}" for site in sites})
    runs_by_path = fetch_runs(
        workflows, api=api, repository=repository, head_sha=head_sha, token=token
    )
    runs = {Path(path).name: value for path, value in runs_by_path.items()}

    fields = evaluate(sites, runs)
    # **ولا حقلَ `commit` هنا.** الأصلُ يُورَث من البيئة في `emit_certification_evidence`
    # ويرفض تمريرَه وسيطاً — لأنّ قبولَه يجعل الباعثَ أداةَ تلفيقٍ جاهزة.
    fields["guard_catalogue"] = "docs/runbooks/GUARD_CATALOGUE.md"
    fields["workflow_runs"] = [
        {"workflow": name, **{k: v for k, v in value.items() if k != "jobs"}}
        for name, value in sorted(runs.items())
    ]
    fields["honesty_limit"] = (
        "يشهد أنّ خطوةً تستدعي كلَّ حارسٍ حاجبٍ انتهت success على هذه البصمة بحسب واجهة "
        "Actions. ولا يشهد أنّ الحارسَ يمسك عطلَه (تلك مواصفاتُ الطفرة)، ولا يجرد إلّا ما "
        "يُستدعى بنمط `python scripts/ci/<x>.py` — نفسُ نطاق كتالوج الحرّاس."
    )
    return fields


def _require_env(name: str) -> str:
    value = str(os.environ.get(name) or "").strip()
    if not value:
        raise SystemExit(f"متغيّرُ البيئة {name} غائب — لا شاهدَ يُجمَع خارج عدّاء GitHub Actions.")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, help="ملفّ حقول القياس (JSON)")
    args = parser.parse_args(argv)

    fields = collect()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fields, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    proven, declared = fields["guards_proven_run"], fields["guards_declared"]
    print(f"GUARDS witness: {proven}/{declared} حارساً حاجباً أُثبِت تشغيلُه → {out}")
    if fields["guards_unproven"]:
        # **الفارقُ يُطبَع لا يُختصَر عدداً.** قائمةٌ محدودةٌ في السطور وكاملةٌ في الملفّ:
        # العددُ وحدَه هو بعينه ما رفضه إعلانُ المُنتِجين.
        print(f"✗ لم يُثبَت تشغيلُ {len(fields['guards_unproven'])} حارساً على هذه البصمة:")
        for item in fields["guards_unproven"][:40]:
            print(f"  − {item['guard']}: {', '.join(item['reasons'])}")
        if len(fields["guards_unproven"]) > 40:
            print(f"  … و{len(fields['guards_unproven']) - 40} غيرها في {out}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
