#!/usr/bin/env python3
"""يجمع شاهدَ `P-CERT-1` من **عدّاء CI الحقيقيّ على هذه البصمة**، لا من مِسبارِ دخان.

`P-CERT-1-EVIDENCE-WOULD-OVERCLAIM-A-SMOKE-RUN-01`.

الحاجبُ اسمُه «Full branch CI»، ووظيفتُه في `production-certification-blockers.yml`
تُشغّل `runtime_real_smoke.sh` وحدَه. فانبعاثُ `verified` من هناك يقول «CI الفرعِ
كاملاً مرّ» بينما المقيسُ **مِسبارُ دخان** — وهو بعينه صنفُ الادّعاء الذي بُنيت حزمةُ
الأدلّة كلُّها لمنعه، مقلوباً على نفسه: أداةُ الصدق تصير مصدرَ الكذبة.

فالشاهدُ يُطلَب من مصدره: واجهةُ Actions تُسأل عن أعدية `ci.yml` على `GITHUB_SHA`،
ولا يُقبَل إلّا عدّاءٌ **مكتملٌ وخُلاصتُه `success`**. وأسماءُ الوظائف وخُلاصاتُها
تُنقَل كما هي — لا تُلخَّص بعدد، فالعددُ يُخفي أيَّ وظيفةٍ تخطّت.

**ويفشل مفتوحاً على الغياب لا مغلقاً على التخمين:** لا عدّاء ⇒ سقوط، عدّاءٌ فاشل ⇒
سقوط، عدّاءٌ قيدَ التشغيل ⇒ سقوط. وسقوطُ الجامع يترك الحاجبَ `pending`، فالحكمُ
`production_certified=false` — لا اعتمادَ بلا شاهد.

**حدُّ صدقٍ مُعلَن:** هذا يشهد أنّ عدّاءً بهذا الاسم على هذه البصمة انتهى ناجحاً
بحسب واجهةِ GitHub. ولا يشهد أنّ ذلك العدّاء شغّل البوّابات التي نظنّها فيه — تلك
حقيقةٌ في `ci.yml` نفسه، يحرسها `preflight_required` وكتالوجُ الحرّاس لا هذا الملفّ.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORKFLOW_PATH = ".github/workflows/ci.yml"

#: الخُلاصةُ الوحيدةُ المقبولة. `skipped` و`neutral` **ليستا نجاحاً**: تعنيان أنّ
#: العدّاء لم يقِس، وقبولُهما يحوّل «لم يُقَس» إلى «مرّ» — الصنفُ الذي يوثّقه
#: `preflight.sh` في `need()` بإعلانه التخطّي بصوتٍ عالٍ بدل تمريره صامتاً.
_ACCEPTED_CONCLUSION = "success"


def _api(url: str, token: str) -> dict:
    request = urllib.request.Request(  # noqa: S310 — مخطّطٌ مُثبَّت أدناه
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "sahool-certification-evidence",
        },
    )
    if urllib.parse.urlparse(url).scheme != "https":
        raise SystemExit(f"واجهةٌ بمخطّطٍ غير https مرفوضة: {url}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"طلبُ الواجهة سقط ({exc.code}) على {url}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise SystemExit(f"تعذّر بلوغُ واجهة Actions: {exc}") from exc


def _require_env(name: str) -> str:
    value = str(os.environ.get(name) or "").strip()
    if not value:
        raise SystemExit(f"متغيّرُ البيئة {name} غائب — لا شاهدَ يُجمَع خارج عدّاء GitHub Actions.")
    return value


def resolve_workflow_id(api: str, repository: str, workflow_path: str, token: str) -> int:
    """يُحوِّل **مسارَ** الـworkflow إلى معرّفه الرقميّ بالسؤال، لا بافتراضِ شكلِ المُعرِّف.

    **مراجعةٌ آليّةٌ أصابت:** كانت الصيغةُ السابقة تُمرِّر المسارَ الكامل
    (`.github/workflows/ci.yml`) في موضع `{workflow_id}`، ونقطةُ الواجهة توثَّق أنّها
    تقبل **معرّفاً رقميّاً أو اسمَ الملفّ**. فالمسارُ الكامل يُرجِع `404` على الأرجح.

    **ولمَ هذا أخطرُ من عطلِ مسارٍ عاديّ:** السقوطُ كان سيُقرأ «لا عدّاءَ CI على هذه
    البصمة» — أي **عطلٌ يتنكّر في زيّ عُطلٍ آخر**، فيبقى `P-CERT-1` مُعلَّقاً إلى الأبد
    ويُقرأ ذلك تقصيراً في تشغيل CI لا خطأً في السطر. وهو الصنفُ نفسُه الذي أُغلِق في
    `tenant_connection` هذه الجلسة.

    **ولم أُرجِّح بين قراءتَي التوثيق بالظنّ:** تعذّر قياسُ سلوك النقطة من هذه الحاوية
    (الوسيطُ يردّ `403` على الطلب غير المُصادَق، ولا يُلتَفُّ حوله). فأُزيل الاعتمادُ
    على الجواب أصلاً: تُسأل قائمةُ الـworkflows ويُطابَق حقلُ `path` **بيانات**، ثمّ
    يُستعمَل `id` الرقميّ — وهو صحيحٌ تحت القراءتين معاً، ويحوّل المسارَ من مُعرِّفٍ
    مفترَض إلى حقيقةٍ مقيسة.
    """
    page = 1
    seen: list[str] = []
    while page <= 10:  # سقفٌ صريح: قائمةٌ بلا نهايةٍ عطلٌ لا انتظار
        payload = _api(
            f"{api}/repos/{repository}/actions/workflows?per_page=100&page={page}", token
        )
        workflows = payload.get("workflows", [])
        if not workflows:
            break
        for workflow in workflows:
            if str(workflow.get("path") or "") == workflow_path:
                return int(workflow["id"])
            seen.append(str(workflow.get("path") or ""))
        if len(workflows) < 100:
            break
        page += 1
    raise SystemExit(
        f"لا workflow مسارُه {workflow_path} في {repository} — "
        f"المسارات المرصودة ({len(seen)}): {', '.join(sorted(seen)[:8])}…\n"
        "وهذا **ليس** «لا عدّاءَ على هذه البصمة»: المُعرِّفُ نفسُه لم يُحلَّ."
    )


def collect(workflow_path: str = DEFAULT_WORKFLOW_PATH) -> dict:
    repository = _require_env("GITHUB_REPOSITORY")
    head_sha = _require_env("GITHUB_SHA")
    token = str(os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    if not token:
        raise SystemExit("لا رمزَ وصول (GITHUB_TOKEN) — امنح الوظيفة `permissions: actions: read`.")
    api = str(os.environ.get("GITHUB_API_URL") or "https://api.github.com").rstrip("/")

    workflow_id = resolve_workflow_id(api, repository, workflow_path, token)
    runs = _api(
        f"{api}/repos/{repository}/actions/workflows/{workflow_id}/runs"
        f"?head_sha={urllib.parse.quote(head_sha)}&per_page=20",
        token,
    ).get("workflow_runs", [])
    if not runs:
        raise SystemExit(
            f"لا عدّاءَ لـ{workflow_path} على {head_sha[:8]}… — شغّل CI على هذه البصمة أوّلاً."
        )

    # الأحدثُ أوّلاً كما تُرجعها الواجهة؛ ويُختار أوّلُ **مكتملٍ** لا أوّلُ ما ورد،
    # لأنّ إعادةَ تشغيلٍ قيدَ العمل تتصدّر القائمة وهي بلا خُلاصة.
    completed = [r for r in runs if r.get("status") == "completed"]
    if not completed:
        raise SystemExit(
            f"عدّاءات {workflow_path} على {head_sha[:8]}… لم يكتمل منها شيء — انتظر انتهاءها."
        )
    run = completed[0]
    conclusion = str(run.get("conclusion") or "")
    if conclusion != _ACCEPTED_CONCLUSION:
        raise SystemExit(
            f"عدّاءُ CI رقم {run.get('id')} خُلاصتُه {conclusion!r} لا {_ACCEPTED_CONCLUSION!r} — "
            "لا شاهدَ لحاجبٍ غيرِ قابلٍ للإعفاء."
        )

    jobs_payload = _api(
        f"{api}/repos/{repository}/actions/runs/{run['id']}/jobs?per_page=100", token
    )
    jobs = [
        {"name": job.get("name"), "conclusion": job.get("conclusion")}
        for job in jobs_payload.get("jobs", [])
    ]
    if not jobs:
        raise SystemExit(f"عدّاءُ CI رقم {run['id']} بلا وظائف — شاهدٌ خاوٍ ليس شاهداً.")

    # خُلاصةُ العدّاء `success` ولا تمنع وظيفةً `skipped` داخلَها. تُنقَل كما هي
    # وتُسمّى: الحكمُ يبقى عند الحارس، والإخفاءُ هنا كان سيجعله يحكم على أقلّ ممّا جرى.
    return {
        "branch": run.get("head_branch") or head_sha,
        "commit": run.get("head_sha") or head_sha,
        "jobs": jobs,
        "ci_workflow_path": workflow_path,
        "ci_run_id": str(run.get("id")),
        "ci_run_url": run.get("html_url"),
        "ci_run_conclusion": conclusion,
        "ci_jobs_not_success": sorted(
            {str(j["conclusion"]) for j in jobs if j["conclusion"] != _ACCEPTED_CONCLUSION}
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workflow-path", default=DEFAULT_WORKFLOW_PATH)
    parser.add_argument("--out", required=True, help="ملفّ حقول القياس (JSON)")
    args = parser.parse_args(argv)

    fields = collect(args.workflow_path)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fields, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"P-CERT-1 witness collected from run {fields['ci_run_id']} → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
