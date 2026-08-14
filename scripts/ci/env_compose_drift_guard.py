#!/usr/bin/env python3
"""حارس انجراف env↔compose (السجل التشغيليّ #3) — صنف عضّ مرتين، فأُغلِق بحارس.

**لماذا:** httpx غير المعلَن في CI، وJWT_SECRET المقروء بلا تزويد (اكتُشِف بالصدفة) — «كود يقرأ env
وcompose لا يزوّدها». صنف عضّ مرتين ⇒ سيعضّ ثالثة. بُني (ذروة الحُرّاس) رخيصاً.

**التطوّر (شرط المالك ④): تقرير أوّلاً ثمّ حارس.** بُدِئ تقريراً (v1: 32 مفقود جُرِدت وصُنِّفت)، ثمّ
راجعنا كلّ عنصر (بما فيها 5 مشتبَهات فُحِصت سطراً-سطراً: soil/redis-rate/worker-id/rls-bypass/actuator —
كلّها «تنحدر بوضوح» أو «افتراضيّ آمن»، لا كسر صامت)، فقُلِب حارساً حازماً: ``--check`` الآن **يُحمِّر**
(exit 1) على أيّ مفقود غير مُصنَّف في قائمة الاستثناء. ``--report`` يبقى إرشاديّاً (exit 0) للجرد.

**النطاق الذكي (شروط المالك ①②③):**
  ① المطلوب ظاهريّاً فقط: ``os.getenv("X")`` بلا افتراضيّ · ``os.environ["X"]`` · ``os.environ.get("X")``
     بلا افتراضيّ. ذوات الافتراضيّات (``getenv("X","d")``) **خارج النطاق** (آمنة التصميم).
  ② المطابقة ضدّ compose **و** .env.example: موثَّق في .env.example وغائب من compose ⇒ «محقون» (secret
     manager إنتاجاً) لا «مفقود».
  ③ قائمة استثناء معلَّبة بتعليل لكلّ عنصر (تُراجَع كمراجعة كود، لا تُولَّد آليّاً).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01: مخرَجُ هذا الحارس عربيّ،
# و`print` يُرمّز بلغة الآلة. فتحت `LC_ALL=C` كان يحسب **صحيحاً** ثمّ يموت وهو يطبع
# نجاحه (UnicodeEncodeError) ⇒ خروجٌ بـ1 يُقرَأ «الحارس يحجب» وهو قد مرّ. وحارسٌ
# يُبلِغ فشلاً لأنّه عجز عن طباعة نجاحه أسوأ من حارسٍ صامت: الصامت يُرى غيابُه،
# وهذا يُرى **ضدّ** ما قاس. القراءة محكومة بأساسٍ قائم؛ والمنسيّ كان الكتابة.
# **عند التحميل لا داخل `main()`** — فبعض الحرّاس بلا `main` أصلاً، تطبع من جسدها.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST = Path(__file__).with_name("env_compose_drift_allowlist.json")

# ── ① المطلوب ظاهريّاً (بلا افتراضيّ) ──
_GETENV_NO_DEFAULT = re.compile(r"""os\.getenv\(\s*["']([A-Z_][A-Z0-9_]*)["']\s*\)""")
_ENVIRON_INDEX = re.compile(r"""os\.environ\[\s*["']([A-Z_][A-Z0-9_]*)["']\s*\]""")
_ENVIRON_GET_NO_DEFAULT = re.compile(r"""os\.environ\.get\(\s*["']([A-Z_][A-Z0-9_]*)["']\s*\)""")

# ── ② مزوَّد في compose (مرجع ${VAR} أو مفتاح بيئة) / معلَن في .env.example ──
_COMPOSE_REF = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)")
_COMPOSE_ENVKEY = re.compile(r"^\s{6,}([A-Z_][A-Z0-9_]*):", re.M)
_ENV_DECL = re.compile(r"^\s*([A-Z_][A-Z0-9_]*)\s*=", re.M)

# ثوابت لغة/إطار شائعة تُقرأ بلا افتراضيّ لكنّها ليست تزويد-تشغيل (لا تُطابَق ضدّ compose).
_RUNTIME_NOISE = {"PATH", "HOME", "PWD", "PYTHONPATH", "TZ", "LANG", "LC_ALL", "USER", "HOSTNAME"}


def required_env_vars(text: str) -> set[str]:
    """المتغيّرات المقروءة **بلا افتراضيّ** (مطلوبة ظاهريّاً) — شرط ①."""
    out: set[str] = set()
    for rx in (_GETENV_NO_DEFAULT, _ENVIRON_INDEX, _ENVIRON_GET_NO_DEFAULT):
        out.update(rx.findall(text))
    return out - _RUNTIME_NOISE


def compose_provided_vars(text: str) -> set[str]:
    return set(_COMPOSE_REF.findall(text)) | set(_COMPOSE_ENVKEY.findall(text))


def env_example_vars(text: str) -> set[str]:
    return set(_ENV_DECL.findall(text))


def classify(
    required: dict[str, list[str]],
    compose_provided: set[str],
    env_declared: set[str],
    allowlist: set[str],
) -> dict[str, list[dict]]:
    """يصنّف كلّ متغيّر مطلوب: provided (compose) · injected (env.example فقط) · missing (لا هذا ولا ذاك)."""
    buckets: dict[str, list[dict]] = {"missing": [], "injected": [], "provided": []}
    for var, sources in sorted(required.items()):
        if var in allowlist:
            continue
        row = {"var": var, "read_in": sorted(set(sources))[:6]}
        if var in compose_provided:
            buckets["provided"].append(row)
        elif var in env_declared:
            buckets["injected"].append(row)  # ② موثَّق/محقون (secret manager) لا مفقود
        else:
            buckets["missing"].append(row)
    return buckets


def _scan_repo() -> dict:
    required: dict[str, list[str]] = {}
    for path in (ROOT / "services").rglob("*.py"):
        if "__pycache__" in path.parts or path.name.startswith("test_"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for var in required_env_vars(text):
            required.setdefault(var, []).append(str(path.relative_to(ROOT)))

    compose_provided: set[str] = set()
    for cf in ROOT.glob("docker-compose*.yml"):
        compose_provided |= compose_provided_vars(cf.read_text(encoding="utf-8", errors="ignore"))
    env_declared = env_example_vars(
        (ROOT / ".env.example").read_text(encoding="utf-8", errors="ignore")
    )

    allowlist = set()
    if ALLOWLIST.exists():
        allowlist = set(json.loads(ALLOWLIST.read_text(encoding="utf-8")).get("intentional", {}))
    return {
        "buckets": classify(required, compose_provided, env_declared, allowlist),
        "allow": len(allowlist),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--check",
        action="store_true",
        help="حازم: يُحمِّر (exit 1) على أيّ مفقود غير مُصنَّف في قائمة الاستثناء",
    )
    ap.add_argument("--report", action="store_true", help="إرشاديّ: يطبع الجرد كاملاً ويخرج 0")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    res = _scan_repo()
    b = res["buckets"]
    missing = b["missing"]
    if args.json:
        print(json.dumps(b, ensure_ascii=False, indent=2))
        return 1 if (args.check and missing) else 0
    print(
        f"env↔compose drift: missing(unclassified)={len(missing)} · "
        f"injected(env.example only)={len(b['injected'])} · provided={len(b['provided'])} · "
        f"allowlisted={res['allow']}"
    )
    for row in missing:
        print(f"  MISSING: {row['var']}  ← {', '.join(row['read_in'][:3])}")
    if args.check and missing:
        print(
            "\n✗ انجراف env↔compose: المتغيّرات أعلاه تُقرأ بلا افتراضيّ وغائبة من compose و.env.example "
            "وغير مُصنَّفة في scripts/ci/env_compose_drift_allowlist.json.\n"
            "  الإصلاح: (١) إن كانت مقصودة (راية/سرّ/عنوان بيئة) صنّفها في القائمة بتبرير؛ "
            "(٢) وإلّا زوّدها في compose أو وثّقها في .env.example.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
