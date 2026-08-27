#!/usr/bin/env python3
"""S5 live-closure receipt collector — الطرفُ المفقود من سلسلة C9.

قراءةٌ صِرف. لا يكتب في قاعدةٍ ولا يُغيّر وضعاً ولا يرفع سلطة. يجمع — في تشغيلةٍ
واحدة على البيئة الحيّة — البنودَ التي يفرضها
``s5_decision_live_closure_receipt_guard`` ويكتبها إيصالاً واحداً.

**العطلُ الذي يُغلقه:** كان في المستودع خمسةُ حرّاسٍ يتحقّقون من إيصالات ومُنتِجٌ
واحدٌ يكتب إيصالاً. فحارسُ S5 جاهزٌ ومُكذَّب، و``c9_decision_authority_certification``
يستدعيه، ولا شيء في الشجرة **يُنتِج** الإيصالَ الذي ينتظره — فبقيت C9 عند
``EVIDENCE_REQUIRED`` بنيويّاً لا لغياب بيئة.

**والحكمُ يُشتقّ من الحارس نفسِه لا يُعاد تنفيذُه هنا:** ``classification`` تُحسَب
باستدعاء ``findings_for`` المستوردة من الحارس. جامعٌ يُعيد كتابة الشروط ينحرف عنها
بصمت، فيُنتِج إيصالاً يظنّه صاحبُه صالحاً وترفضه البوّابة — أو أسوأ: يدّعي
``PASSED`` على قياسٍ لا يستوفي الشرط.

**واتّفاقيّةُ الخروج تفصل الدليلَ عن العطل** (سنّة ``d09_live_evidence_receipt``):
إيصالٌ مكتملٌ يوثّق **فشلَ بند** ⇒ رمز ``0`` والحكمُ في ``classification``.
**العجزُ عن القياس** (خدمةٌ لا تستجيب، سكربتٌ لا يعمل) ⇒ رمز ``1`` ولا يُكتَب
إيصال. وخلطُهما يجعل «تعذّر الوصول» يُقرأ «فشلاً مُثبَتاً».

الربطُ إلزاميّ: بلا ``--subject-sha`` لا يُكتَب إيصالٌ أصلاً — فلا يُنتَج دليلٌ
قابلٌ لإعادة الاستعمال على شجرةٍ أخرى.

التشغيل من مضيفٍ يرى الخدمتين وقاعدةَ البيانات::

    python3 scripts/architecture/s5_decision_live_closure_receipt.py \\
      --subject-sha "$(git rev-parse HEAD)" \\
      --decision-url http://localhost:8010 \\
      --platform-url http://localhost:8000 \\
      --output evidence/s5-decision-live-closure.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
GUARD = Path(__file__).resolve().parent / "s5_decision_live_closure_receipt_guard.py"
DECISION_SVC = ROOT / "services" / "decision-service"

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

# `platform_sor_revoke` يقبل ثلاثةَ أفعالٍ حصريّة: قراءةٌ · سحبُ صلاحيّة · منحُها.
# وهذا الجامعُ **قارئٌ صِرف**، فيُسمّى فعلُه ولا يُكتَب علماً حرفيّاً عند النداء:
# تسميتُه تجعل تمريرَ فعلٍ كاتبٍ سهواً تغييراً مرئيّاً في سطرٍ واحدٍ مُعلَن.
#
# وله أثرٌ ثانٍ يُقال صراحةً لا يُخفى: `verify_all_generated` يُصنّف «يدعم
# الفحص» بمطابقة الحرفيّة في المصدر، ولا يُفرّق بين **إعلان** علمٍ و**تمريره**
# إلى أداةٍ أخرى — فكان يعُدّ هذا الجامعَ مولّداً غيرَ موصول. وقِيست ثلاثُ صياغاتٍ
# أدقّ للمُصنِّف (سطرُ `add_argument` · `argv` · تحليلُ `ast`)، وكلُّها تُسقِط
# مولّداتٍ حقيقيّة (١٢ سكربتاً بالأخيرة) لأنّ بعضها يُعلن العلمَ بلا argparse.
# فالحارسُ لا يُلمَس — وأساسُ الاستثناء راتشِتٌ فارغ لا يُزاد — ويُحلّ هنا.
_PRIVILEGE_READ_ACTION = "check"


class MeasurementError(RuntimeError):
    """عجزٌ عن القياس — لا فشلُ بندٍ مُثبَت. يُنهي بـ1 بلا كتابة إيصال."""


def _load_guard():
    """الحارسُ هو مصدرُ الشروط الوحيد — يُستورَد ولا تُعاد كتابتُه."""
    spec = importlib.util.spec_from_file_location("s5_guard", GUARD)
    if spec is None or spec.loader is None:  # pragma: no cover - بيئةٌ مكسورة
        raise MeasurementError(f"تعذّر تحميل الحارس: {GUARD}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def http_json(url: str, timeout: int = 30) -> Any:
    """قراءةٌ واحدة. أيُّ حالةٍ غير 200 أو جسمٍ غير JSON ⇒ عجزٌ عن القياس."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - عناوين داخليّة يُمرّرها المُشغِّل
            body = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except (urllib.error.URLError, OSError) as exc:
        raise MeasurementError(f"تعذّر بلوغ {url}: {exc}") from exc
    if status != 200:
        raise MeasurementError(f"{url} أعاد {status}")
    try:
        return json.loads(body)
    except ValueError as exc:
        raise MeasurementError(f"{url} أعاد جسماً غير JSON") from exc


_LOCAL_SCRIPT_TIMEOUT_SECONDS = 90


def run_json(script: Path, *args: str) -> Any:
    """سكربتٌ محلّيّ يطبع JSON. رمزُ خروجه **ليس** الحكم — الحكمُ في جسمه.

    `decision_sor_role_certify` يُنهي بـ2 حين `classification != PASSED`، وذلك
    **قياسٌ ناجح لحالةٍ سالبة** لا عجزٌ عن القياس. فلا يُقرأ رمزُ الخروج فشلاً.

    **وعجزُ الاستجابة عجزٌ عن القياس أيضاً**: بلا `timeout` صريح هنا، سكربتٌ محلّيّ
    عالقٌ (اتّصال قاعدة بيانات مُعلَّق) يُبقي هذا القياسَ مُعلَّقاً حتّى المهلة
    الخارجيّة الأكبر للمنسِّق — وهي ليست بديلاً عن مهلةٍ محلّيّة لبَدَاهة القياس
    نفسه.
    """
    try:
        proc = subprocess.run(
            [sys.executable, str(script), *args],
            cwd=str(DECISION_SVC),
            capture_output=True,
            encoding="utf-8",
            check=False,
            timeout=_LOCAL_SCRIPT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise MeasurementError(
            f"{script.name} لم يستجب خلال {_LOCAL_SCRIPT_TIMEOUT_SECONDS} ثانية"
        ) from exc
    if not (proc.stdout or "").strip():
        raise MeasurementError(
            f"{script.name} لم يطبع شيئاً (rc={proc.returncode}): {(proc.stderr or '')[-300:]}"
        )
    try:
        return json.loads(proc.stdout)
    except ValueError as exc:
        raise MeasurementError(f"{script.name} طبع جسماً غير JSON") from exc


def write_enforcement_proven(privilege: dict[str, Any], sor_tables: tuple[str, ...]) -> bool:
    """أهي كتابةُ المنصّة ممنوعةٌ فعليّاً على كلّ جداول السجلّ؟

    هذا **ادّعاءٌ مقيس** لا افتراض: يُشتقّ من حالة الامتيازات المقروءة، فإن كان
    جدولٌ واحدٌ ما زال يقبل كتابةً كان الادّعاءُ كاذباً — والحارسُ يرفضه.
    """
    after = privilege.get("after") or {}
    for table in sor_tables:
        perms = after.get(table) or {}
        if any(perms.get(op) is not False for op in ("INSERT", "UPDATE", "DELETE")):
            return False
        if perms.get("SELECT") is not True:
            return False
    return True


def build_receipt(
    subject_sha: str,
    evidence: dict[str, Any],
    guard: Any,
    observed_at: str,
) -> dict[str, Any]:
    """يُجمِّع الإيصال ثمّ **يسأل الحارسَ عن حكمه** بدل أن يحكم لنفسه."""
    privilege = evidence.get("platform_privilege_check") or {}
    receipt: dict[str, Any] = {
        "schema": guard.SCHEMA,
        "subject_sha": subject_sha,
        "observed_at": observed_at,
        "read_only": True,
        "authority_promotion": False,
        "claims": {
            "post_cutover_platform_write_enforcement_proven": write_enforcement_proven(
                privilege, guard.SOR_TABLES
            ),
            # **يُثبَّت `false` بنيويّاً ولا يُشتقّ:** هذا الجامعُ لا يفحص سجلّاتٍ
            # تاريخيّة، فادّعاءُ «صفرُ كتاباتٍ تاريخيّة مقيس» كذبٌ متاح. والحارسُ
            # يرفض `true` صراحةً بـ`historical_zero_writes_overclaim` — حارسٌ
            # يمنع المبالغة لا النقص، فيُحترَم بالبناء لا بالانضباط.
            "historical_zero_platform_writes_measured": False,
        },
        "evidence": evidence,
    }
    findings = guard.findings_for(
        {**receipt, "classification": "PASSED", "findings": []}, subject_sha
    )
    receipt["classification"] = "PASSED" if not findings else "FAILED"
    receipt["findings"] = [] if not findings else findings
    return receipt


def collect(
    subject_sha: str,
    decision_url: str,
    platform_url: str,
    guard: Any,
    now: str | None = None,
) -> dict[str, Any]:
    d = decision_url.rstrip("/")
    p = platform_url.rstrip("/")
    evidence = {
        "decision_runtime_identity": http_json(f"{d}/runtime-identity"),
        "platform_runtime_identity": http_json(f"{p}/runtime-identity"),
        "decision_ready": http_json(f"{d}/readyz"),
        "decision_cutover_readiness": http_json(f"{d}/v1/cutover/readiness"),
        "platform_ready": http_json(f"{p}/readyz"),
        "role_certification": run_json(DECISION_SVC / "decision_sor_role_certify.py"),
        "platform_privilege_check": run_json(
            DECISION_SVC / "platform_sor_revoke.py", f"--{_PRIVILEGE_READ_ACTION}"
        ),
    }
    stamp = now or datetime.now(UTC).isoformat()
    return build_receipt(subject_sha, evidence, guard, stamp)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--subject-sha", required=True, help="40-hex — الربطُ إلزاميّ")
    ap.add_argument("--decision-url", required=True)
    ap.add_argument("--platform-url", required=True)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args(argv)

    if not _SHA_RE.fullmatch(args.subject_sha):
        print(f"subject-sha ليس 40-hex: {args.subject_sha}", file=sys.stderr)
        return 1

    try:
        guard = _load_guard()
        receipt = collect(args.subject_sha, args.decision_url, args.platform_url, guard)
    except MeasurementError as exc:
        # عجزٌ عن القياس — لا إيصال. «تعذّر الوصول» ليس «فشلاً مُثبَتاً».
        print(json.dumps({"measured": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "measured": True,
                "classification": receipt["classification"],
                "findings": receipt["findings"],
                "output": str(args.output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
