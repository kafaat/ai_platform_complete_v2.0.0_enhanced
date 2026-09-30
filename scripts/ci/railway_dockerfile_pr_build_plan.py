#!/usr/bin/env python3
"""أيُّ ملفّات Dockerfile التي يبنيها Railway يمسّها هذا الـPR؟ — DOCKER-BUILD-VERIFIED-ONLY-ON-MANUAL-DISPATCH-SKIP-READS-GREEN-01.

وظيفةُ `docker-build` في مصفوفة البناء لا تعمل إلّا بتشغيلٍ يدويّ، فتظهر «skipped» في كلّ PR
وتُقرأ نجاحاً؛ ومع `checkSuites:false` على Railway لا شيء يبني الـDockerfile قبل أن يبنيه
Railway في الإنتاج. هذا المُخطِّط يختار ما يُبنى في الـPR:

* **القائمة** = ملفّات Dockerfile التي يبنيها Railway فعلاً (مقيسةٌ من إعدادات الخدمات،
  `certification/evidence/railway_live_config_20260930.json`) — لا كلّ Dockerfile في الشجرة.
* **السياق مُشتقٌّ لا مُصان:** مصادرُ `COPY`/`ADD` تُقرأ من الـDockerfile نفسه، فتغييرُ ملفٍّ
  يُنسَخ داخل الصورة يختار بناءها — لا الـDockerfile وحده (وإلّا فهو «التخطّي يُقرأ نجاحاً»
  في طبقةٍ أخرى).
* **لا كلّ PR:** ما لا يمسّ Dockerfile ولا سياقَه لا يُبنى.

الإخراج JSON: `{"builds": [{"dockerfile", "service", "reasons"}], "context": {...}}`.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# ملفّات Dockerfile التي يبنيها Railway (المصدر: dockerfilePath في إعداد كلّ خدمة، 2026-09-30).
# السياقُ جذرُ المستودع (`rootDirectory: /`) لكلّها.
RAILWAY_DOCKERFILES: dict[str, str] = {
    "sahool-platform": "services/sahool-platform/Dockerfile",
    "sahool-auth-main": "services/auth/Dockerfile",
    "sahool-frontend": "deploy/railway/Dockerfile.frontend",
    "sahool-raster-service": "services/raster-service/Dockerfile",
    "sahool-notification-agent": "agents/notification/Dockerfile",
    "sahool-migrate-main": "deploy/railway/Dockerfile.migrate",
    "sahool-decision-service": "services/decision-service/Dockerfile",
    "sahool-guardrails-engine": "services/guardrails-engine/Dockerfile",
    "sahool-field-management-service": "services/field-management-service/Dockerfile",
    "sahool-vegetation-analysis": "services/vegetation-analysis-service/Dockerfile",
    "sahool-tts-service": "services/tts-service/Dockerfile",
    "sahool-soil-service": "services/soil-service/Dockerfile",
    "sahool-ai-agronomist": "services/ai_agronomist/Dockerfile",
}

# تغييرُ المُتحقِّق نفسه يُعيد إثباتَ كلّ ما يتحقّق منه: وإلّا فالـPR الذي يُضيفه (أو يكسره)
# لا يبني شيئاً — «لا شيءَ يُبنى» يُقرأ نجاحاً، وهو الصنفُ نفسه الذي وُجد لإغلاقه.
VERIFIER_PATHS = (
    ".github/workflows/railway-dockerfile-pr-build.yml",
    "scripts/ci/railway_dockerfile_pr_build_plan.py",
)

_COPY = re.compile(r"^\s*(?:COPY|ADD)\s+(.*)$", re.IGNORECASE)
_FLAG = re.compile(r"^--[a-z-]+(=\S+)?$", re.IGNORECASE)


def copy_sources(dockerfile_text: str) -> list[str]:
    """مصادرُ COPY/ADD من سياق البناء (لا `--from=` مرحلةٍ أخرى)، مُطبَّعةً بلا `./` ولا شرطةٍ أخيرة."""
    sources: list[str] = []
    for raw in dockerfile_text.replace("\\\n", " ").splitlines():
        match = _COPY.match(raw)
        if not match:
            continue
        tokens = match.group(1).split()
        if any(t.lower().startswith("--from") for t in tokens):
            continue
        tokens = [t for t in tokens if not _FLAG.match(t)]
        if tokens and tokens[0].startswith("["):  # صيغةُ JSON
            try:
                tokens = json.loads(" ".join(tokens))
            except json.JSONDecodeError:
                continue
        for src in tokens[:-1]:  # الأخيرُ هو الوجهة
            src = src.strip().removeprefix("./").rstrip("/")
            if src and src not in sources:
                sources.append(src or ".")
    return sources


def touches(changed: str, source: str) -> bool:
    """هل يقع الملفّ المُعدَّل داخل مصدر COPY؟ (`.` ⇒ السياقُ كلّه)."""
    if source in (".", ""):
        return True
    if any(ch in source for ch in "*?["):
        prefix = re.split(r"[*?\[]", source, maxsplit=1)[0].rstrip("/")
        return changed.startswith(prefix)
    return changed == source or changed.startswith(source + "/")


def plan(changed_files: list[str], root: Path = ROOT, force: list[str] | None = None) -> dict:
    """``force``: خدماتٌ تُبنى بلا شرط (تشغيلٌ يدويّ يُثبت البناءَ نفسه، لا التغيير)."""
    unknown = sorted(set(force or []) - set(RAILWAY_DOCKERFILES))
    if unknown:
        raise ValueError(f"unknown Railway service(s): {', '.join(unknown)}")
    builds = []
    for service, dockerfile in RAILWAY_DOCKERFILES.items():
        path = root / dockerfile
        if not path.exists():
            builds.append(
                {"service": service, "dockerfile": dockerfile, "reasons": ["dockerfile_missing"]}
            )
            continue
        sources = copy_sources(path.read_text(encoding="utf-8"))
        reasons = [f"forced:{service}"] if service in (force or []) else []
        reasons += [f"verifier_changed:{v}" for v in VERIFIER_PATHS if v in changed_files]
        if dockerfile in changed_files:
            reasons.append(f"dockerfile_changed:{dockerfile}")
        for changed in changed_files:
            hit = next((s for s in sources if touches(changed, s)), None)
            if hit:
                reasons.append(f"context_changed:{changed} (COPY {hit})")
        if reasons:
            builds.append({"service": service, "dockerfile": dockerfile, "reasons": reasons})
    return {
        "builds": builds,
        "changed_files": len(changed_files),
        "railway_dockerfiles": len(RAILWAY_DOCKERFILES),
    }


class PlanMissedATouchedDockerfile(RuntimeError):
    """خطّةٌ فارغة لـPR يمسّ Dockerfile: المُطابِقُ معطوب، و«لا شيءَ يُبنى» كذبة."""


def assert_plan_covers_touched_dockerfiles(changed_files: list[str], result: dict) -> None:
    """فحصٌ مستقلّ عن المُطابِق: كلُّ Dockerfile لـRailway في الملفّات المُعدَّلة يجب أن يكون في الخطّة.

    «نُفِّذت الخطّة» لا يكفي — خطّةٌ فارغة نُفِّذت. المطلوبُ «أنتجت ما يستحقّه دخلُها»: عطلٌ في
    المطابقة كان سيُنتج «لا شيءَ يُبنى» ويُقرأ أخضر، وهو الحارسُ الفارغ الذي وُجد هذا لمنعه.
    """
    changed = {c.strip().removeprefix("./") for c in changed_files}
    planned = {b["service"] for b in result.get("builds", [])}
    missed = sorted(
        service
        for service, dockerfile in RAILWAY_DOCKERFILES.items()
        if dockerfile in changed and service not in planned
    )
    if missed:
        raise PlanMissedATouchedDockerfile(", ".join(missed))


def changed_against(base: str, root: Path = ROOT) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(root), "diff", "--name-only", f"{base}...HEAD"],
        capture_output=True,
        encoding="utf-8",
        check=True,
    ).stdout
    return [line for line in out.splitlines() if line]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="origin/main", help="أساسُ المقارنة (merge-base)")
    parser.add_argument("--github-output", help="اكتب matrix=<json> إلى هذا الملفّ")
    parser.add_argument(
        "--force-services",
        default="",
        help="خدماتٌ مفصولةٌ بفواصل تُبنى بلا شرط (all = كلّها)",
    )
    args = parser.parse_args(argv)
    force = [s.strip() for s in args.force_services.split(",") if s.strip()]
    if force == ["all"]:
        force = list(RAILWAY_DOCKERFILES)
    changed = changed_against(args.base)
    result = plan(changed, force=force)
    try:
        assert_plan_covers_touched_dockerfiles(changed, result)
    except PlanMissedATouchedDockerfile as exc:
        print(
            f"railway_dockerfile_pr_build_plan_failed: الخطّةُ فوّتت Dockerfile مُعدَّلاً ({exc})",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    missing = [b for b in result["builds"] if b["reasons"] == ["dockerfile_missing"]]
    if missing:
        print(
            f"railway_dockerfile_pr_build_plan_failed: {len(missing)} Dockerfile مفقود",
            file=sys.stderr,
        )
        return 1
    if args.github_output:
        matrix = [
            {"service": b["service"], "dockerfile": b["dockerfile"]} for b in result["builds"]
        ]
        with open(args.github_output, "a", encoding="utf-8") as fh:
            fh.write(f"matrix={json.dumps(matrix)}\n")
            fh.write(f"count={len(matrix)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
