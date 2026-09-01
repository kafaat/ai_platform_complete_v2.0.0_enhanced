#!/usr/bin/env python3
"""WAIVER-EXPIRY-GUARD — fail CI once a governance waiver has expired.

An ``expiry`` date inside a waiver JSON is inert unless CI actually rejects it once
past — otherwise a temporary exemption silently becomes permanent. This guard scans the
governance waiver config(s) and fails when:

- a waiver's ``expiry`` (``YYYY-MM-DD``) is **before today**, or
- a waiver marked ``temporary: true`` carries **no** ``expiry`` (a temporary waiver
  without an expiry is a latent permanent one), or
- an ``expiry`` value is malformed.

Waivers without ``expiry`` and without ``temporary: true`` are ignored (permanent by
design, e.g. admin-ops routes with no user-facing screen). The guard uses the real
current date at CI time, so an expired waiver forces a deliberate renewal or removal of
the underlying gap.

**And a fourth failure, added because it had already happened silently:** a waiver whose
date lives under a *near-miss* key — ``expires``, ``expires_on``, ``valid_until`` — is
invisible to a guard that reads ``expiry`` alone. It reads as time-boxed to every human
who opens the file and is permanent to CI: the exact outcome this guard exists to
prevent, wearing the guard's own vocabulary. Measured 2026-08-27 on ``e6b1dbaa``:
**seven** entries in ``endpoint_ui_coverage_waivers.json`` carried ``expires``, the
nearest four days out, and the guard had reported ``ok`` over them since they landed.

So the near-miss keys are **rejected, not accepted as aliases**. Accepting them would
close this instance and leave the class open — the next spelling nobody thought of
(``expiration``? ``sunset``?) re-opens it in silence. Rejecting forces one spelling into
the data, where a reader can see it. The repository does use ``expires_on`` elsewhere
(``build_platform_catalog.py`` U4 decisions) with its own enforcement; this rule binds
only the files listed in ``WAIVER_FILES``.
"""

from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

# GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01: مخرَجُ هذا الحارس عربيّ،
# و`print` يُرمّز بلغة الآلة. فتحت `LC_ALL=C` كان يحسب **صحيحاً** ثمّ يموت وهو يطبع
# **فشلَه** (UnicodeEncodeError) ⇒ العطلُ الحقيقيّ (إعفاءٌ انقضى) يُستبدَل بانهيارِ
# ترميزٍ يُخفي سببَه، فيقرأ الناظرُ عطلاً في الترميز حيث العطلُ في الحوكمة.
# **وكشفه التقويمُ لا التغيير:** هذا الحارس لا يطبع عربيّةً إلّا حين يسقط، فبقي
# العطلُ كامناً حتّى أوّلِ انقضاءِ إعفاء — وهو الصنفُ الذي يجعل الحارسَ نفسَه
# نقطةَ العمى. **عند التحميل لا داخل `main()`** — بعض الحرّاس بلا `main` وتطبع
# من جسدها.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]

# Governance waiver files carrying temporary/expiry semantics. Add new files here as
# other subsystems adopt time-boxed waivers.
WAIVER_FILES = (
    ROOT / "config" / "endpoint_ui_coverage_waivers.json",
    ROOT / "config" / "security_exceptions.json",
)


# مرادفاتٌ قريبةٌ تُرفَض. القائمةُ صريحةٌ لا نمطيّة (`.*expir.*`) عمداً: نمطٌ واسع
# يلتقط حقولاً مشروعةً لا علاقةَ لها بانقضاء الإعفاء، فيتحوّل الحارسُ إلى مصدر
# إزعاجٍ يُلتَفّ عليه. وتُزاد هذه القائمةُ حين يظهر تهجٍّ جديد — وظهورُه نفسُه
# يجب أن يكون فشلاً مرئيّاً لا اكتشافاً متأخّراً.
EXPIRY_NEAR_MISS_KEYS = ("expires", "expires_on", "expire", "expiration", "valid_until")


def _iter_waivers(data: object):
    """Yield waiver dicts from either ``{"waivers": [...]}`` or a bare list."""
    if isinstance(data, dict):
        yield from (w for w in data.get("waivers", []) if isinstance(w, dict))
    elif isinstance(data, list):
        yield from (w for w in data if isinstance(w, dict))


def check_waivers(entries: list, *, today: _dt.date) -> list[str]:
    """Return a list of problems (empty ⇒ OK). Pure/deterministic given ``today``."""
    problems: list[str] = []
    for w in entries:
        if not isinstance(w, dict):
            continue
        label = w.get("endpoint") or w.get("id") or "<unknown-waiver>"
        if w.get("temporary") is True:
            required_fields = ("owner", "reason", "scope") if w.get("id") else ("owner", "reason")
            for field in required_fields:
                if not w.get(field):
                    problems.append(f"{label}: temporary waiver missing required field {field}")
        # يُفحَص **قبل** قراءة `expiry`: مُدخَلٌ يحمل الاثنين ما زال مُلتبِساً على
        # قارئه، ومُدخَلٌ يحمل المرادفَ وحدَه كان يمرّ صامتاً — وكلاهما يُبلَّغ.
        for alias in EXPIRY_NEAR_MISS_KEYS:
            if alias in w:
                problems.append(
                    f"{label}: expiry-like field {alias!r}={w[alias]!r} is not read by this "
                    "guard — rename it to 'expiry' (a date CI cannot see is not a deadline)"
                )
        expiry = w.get("expiry")
        if expiry in (None, ""):
            if w.get("temporary") is True:
                problems.append(f"{label}: temporary waiver has no expiry (would be permanent)")
            continue
        try:
            exp = _dt.date.fromisoformat(str(expiry))
        except ValueError:
            problems.append(f"{label}: malformed expiry {expiry!r} (want YYYY-MM-DD)")
            continue
        if exp < today:
            owner = w.get("owner") or w.get("tracking") or w.get("reason_category") or "?"
            problems.append(
                f"{label}: waiver expired {exp.isoformat()} "
                f"(owner={owner}, today={today.isoformat()}) — "
                "resolve the tracked gap or renew the waiver deliberately"
            )
    return problems


def main() -> int:
    today = _dt.date.today()
    problems: list[str] = []
    scanned = 0
    for f in WAIVER_FILES:
        if not f.exists():
            continue
        scanned += 1
        data = json.loads(f.read_text(encoding="utf-8"))
        for p in check_waivers(list(_iter_waivers(data)), today=today):
            problems.append(f"{f.relative_to(ROOT)}: {p}")
    if problems:
        print("waiver_expiry_guard_failed")
        print("\n".join(problems))
        return 1
    print(f"waiver_expiry_guard_ok (scanned {scanned} waiver file(s); today={today.isoformat()})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
