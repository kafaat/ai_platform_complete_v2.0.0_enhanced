#!/usr/bin/env python3
"""حارس إبطال الافتراض الآمن: `.env.example` لا يجوز أن يهزم افتراضَ `compose` إلى `localhost`.

**العطل المقيس على بيئةٍ حيّة (2026-08-12):** أربعة عمّال مفصولون عن NATS. والسبب لم
يكن إعداداً خاطئاً من المشغِّل، بل أنّ المستودع نفسه يطلب نسخ `.env.example` إلى `.env`،
وفيه ‏`NATS_URL=nats://localhost:4222`. و`compose` يستوفي المتغيّر في ستّ خدمات بصيغة
`${NATS_URL:-nats://sahool-nats:4222}` — والافتراضيّ `:-` **لا يعمل إلّا إذا كان
المتغيّر غير مضبوط**. فالملفّ المُوصى بنسخه يُبطِل الافتراض الآمن، و`localhost` داخل
الحاوية هي الحاوية نفسها فينفصل العامل بلا رسالة خطأ واضحة.

**ولماذا لا يُغني `env_compose_drift_guard`:** ذاك يفحص **الحضور** — كودٌ يقرأ متغيّراً
و`compose` لا يزوّده. وهنا الحضور سليم تماماً: `NATS_URL` موجودٌ في الثلاثة. العطل في
**القيمة**، وهو محورٌ لا يراه حارس الحضور.

**والقاعدة تُشتقّ من `compose` لا من قائمةٍ يدويّة:** يُقرأ كلّ `${VAR:-default}`، فإن
كان الافتراضيّ عنواناً إلى **مضيف حاوية** وكانت قيمة `.env.example` إلى `localhost`
أو `127.0.0.1` ⇒ مخالفة. فلا تَبيت القائمة بحركة الشجرة، ولا تحتاج صيانة.

**ولا يُجرَّم `localhost` لغرضه المشروع:** إن كان افتراضُ `compose` نفسه `localhost`
(‏`CORS_ORIGINS` · `DOMAIN`) فالمقصود المضيف، فلا مخالفة. والمتغيّرات التي يكتبها
`compose` **حرفيّاً** (‏`REDIS_URL` في اثنتي عشرة خدمة) خارج النطاق بالبناء — لأنّها
لا تُستوفى من البيئة أصلاً، فقيمةُ `.env.example` فيها تخدم التشغيل خارج compose.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.v9.yml"
ENV_EXAMPLE = ROOT / ".env.example"

_INTERPOLATED = re.compile(r"\$\{([A-Z_][A-Z0-9_]*):-([^}]*)\}")
_LOOPBACK = re.compile(r"//(localhost|127\.0\.0\.1)\b")


def compose_defaults(text: str) -> dict[str, str]:
    """كلّ `${VAR:-default}` في compose. الأوّل يفوز عند التكرار (القيمة نفسها عمليّاً)."""
    out: dict[str, str] = {}
    for match in _INTERPOLATED.finditer(text):
        out.setdefault(match.group(1), match.group(2))
    return out


def env_values(text: str) -> dict[str, str]:
    """`KEY=value` من `.env.example`؛ التعليقات والفراغ تُتجاهَل."""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def violations(defaults: dict[str, str], env: dict[str, str]) -> list[str]:
    """منطق نقيّ: أيّ متغيّرٍ يُبطِل `.env.example` افتراضَه الآمن في compose؟"""
    problems: list[str] = []
    for var, default in sorted(defaults.items()):
        if var not in env:
            continue
        if "://" not in default:
            continue  # ليس عنواناً — لا معنى لـlocalhost فيه
        if _LOOPBACK.search(default):
            continue  # compose نفسه يقصد المضيف (CORS/DOMAIN) — غرضٌ مشروع
        if not _LOOPBACK.search(env[var]):
            continue
        problems.append(
            f"{var}: افتراض compose `{default}` (مضيف حاوية) يُبطِله `.env.example` "
            f"بـ`{env[var]}`. والافتراضيّ `:-` لا يعمل إلّا إذا كان المتغيّر غير مضبوط، "
            "و`localhost` داخل الحاوية هي الحاوية نفسها — استعمل اسم الخدمة."
        )
    return problems


def _read(path: Path) -> str:
    """قراءةٌ fail-closed: ملفٌّ مفقود ليس «لا انجراف» بل **تعذّر قياس**."""
    if not path.is_file():
        print(f"env_compose_default_override_guard_failed: مفقود: {path}")
        raise SystemExit(2)
    return path.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="حارس إبطال افتراض compose الآمن")
    parser.add_argument("--compose", default=str(COMPOSE))
    parser.add_argument("--env", default=str(ENV_EXAMPLE))
    args = parser.parse_args(argv)

    defaults = compose_defaults(_read(Path(args.compose)))
    env = env_values(_read(Path(args.env)))
    if not defaults:
        print("env_compose_default_override_guard_failed: لا افتراضات مُستوفاة — حارسٌ لا يقيس شيئاً")
        return 2

    problems = violations(defaults, env)
    if problems:
        print("env_compose_default_override_guard_failed")
        print("\n".join(f"- {p}" for p in problems))
        return 1

    compared = sum(1 for v in defaults if v in env)
    print(
        f"env_compose_default_override_guard_ok "
        f"(افتراضات مُستوفاة: {len(defaults)} · مُقارَنة بـ.env.example: {compared})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
