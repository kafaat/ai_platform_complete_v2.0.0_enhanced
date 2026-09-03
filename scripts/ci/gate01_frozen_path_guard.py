#!/usr/bin/env python3
"""حارس المسارات المجمَّدة خلف GATE-01 — بوّابةُ **تفويضٍ مقيَّد**، لا مفتاحٌ ثنائيّ.

**العطل الذي وُجِد هذا النموذج لأجله:** الصيغة الأولى كانت `state` = OPEN/CLOSED وحدها،
فلا تستطيع تمثيل الحالة المشروعة التالية: *البوّابة مغلقة عالميّاً، ولهذه الرقعة بعينها
على هذه البايتات بعينها إذنُ مالكٍ بعد تجميد أدلّة المرحلة ٠*. فكان الخياران الوحيدان
**فتحَ كلّ المسارات لأجل رقعة** أو **ردَّ إصلاحٍ صحيح** — والمشكلة في نموذج الحالة لا
في الحارس: كان يعمل كما صُمِّم، وتصميمُه أفقر من القرارات الحقيقيّة.

شجرة القرار::

    مسارٌ مجمَّد مُعدَّل؟
        ├─ لا  ⇒ PASS
        └─ نعم
             البوّابة OPEN؟
               ├─ نعم ⇒ PASS  (انتقالُ مرحلةٍ قُبِل نهائيّاً)
               └─ لا
                    تفويضٌ مقيَّد مطابق؟
                      ├─ لا  ⇒ BLOCK
                      └─ نعم ⇒ الأساس مطابق؟ · المسارات مجموعةٌ جزئيّة؟
                                 · بصمة البايتات مطابقة؟ · غير مُستهلَك؟
                                    ├─ أيٌّ منها لا ⇒ BLOCK
                                    └─ كلّها نعم   ⇒ PASS

**والفصل بين السياسة والتفويض مقصود:** `gate01_policy.json` يجيب «ما الذي يُحمى وبأيّ
مرحلة»، و`gates/adjudications/*.json` يجيب «من أذن وبأيّ نطاق». (والسياسة تبقى في
`docs/architecture/` مباشرةً لا في مجلَّد فرعيّ، لأنّ `claim_base_guard` يمسح المستوى
الأعلى وحده — فنقلُها كان يُخرِجها من فحصٍ قائم يُلزِمها ختمَ تحكيم.) وهما ليسا مصدرَي
حقيقةٍ متنافسين بل سياسةٌ ونسخةُ تفويض — كسياسة RBAC مقابل رمز وصول: الأولى تدوم
والثانية تُستهلَك.

**والربط بالبايتات لا بالاسم:** `authorized_patch_sha256` يُحسَب على نصٍّ قانونيّ من
`path\\0blob_sha` مرتّبةً. فالقرار «أوافق على هذه البايتات» لا «أوافق على PR رقم كذا»،
وتغيُّر محرفٍ واحد في مسارٍ مسموح يُبطِل التفويض. وينجو من الدمج وإعادة الأساس ما دامت
البايتات المأذونة نفسها.

**وكلّ فرعٍ يفشل مغلقاً:** تفويضٌ مشوَّه، أو أساسٌ مخالف، أو مسارٌ زائد، أو بصمةٌ لا
تطابق، أو مُستهلَك ⇒ حجب. فملفٌّ لا يُحلَّل ليس إذناً.

**وحدّ صدقٍ مكتوب:** هذا يمنع **مسّاً غير مأذون** ولا يفعل غير ذلك — لا يفتح البوّابة،
ولا يُثبِّت أدلّة، ولا يحكم على صحّة التعديل. وخضرتُه تعني «لم يُمَسّ مجمَّدٌ بلا إذنٍ
مطابق»، وصحّةُ الرقعة تقيسها اختباراتها وطفراتها.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

# ── ترميزُ الخرج عند التحميل — `GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01`
#
# **العطلُ مقيسٌ لا متوقَّع:** تحت `LC_ALL=C` يحسب هذا الحارسُ حكمَه صحيحاً ثمّ يموت
# بـ`UnicodeEncodeError` **وهو يطبعه** — فيخرج برمزٍ غيرِ رمزه، ويُقرأ حجباً وهو قد
# مرّ (أو العكس). والرسالةُ التي تشرح السبب هي نفسُها ما يقتله.
#
# **ولماذا ظهر الآن ولم يظهر قبل:** الاستدعاءُ العاري (بلا `--stdin`) كان يطبع
# `gate01_frozen_path_guard_ok` وحدَه — ASCII خالص. ومع أوّل تفويضٍ `ISSUED` حيٍّ في
# الشجرة صار `stale_authorization_errors` يُخرِج عربيّةً على الاستدعاء العاري
# (لأنّ `touched` فارغةٌ فيه)، فانكشفت هشاشةٌ **كانت قائمةً دائماً** ولم تجد ما
# تطبعه. أي أنّ الشريحة لم تُحدِث العطل بل أزالت الصمتَ عنه.
#
# **والموضعُ عند التحميل لا داخل `main()`:** الحارسُ يُستورَد في الاختبارات وتُستدعى
# دوالُّه مباشرةً، فعلاجٌ داخل `main()` يترك المسارَ المُستورَد مكشوفاً.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "docs" / "architecture" / "gate01_policy.json"
ADJUDICATIONS = ROOT / "docs" / "architecture" / "gates" / "adjudications"


def _load(path: Path) -> dict:
    """قراءةٌ تفشل مغلقةً: ملفٌّ مفقود أو لا يُحلَّل ليس سياسةً ولا إذناً."""
    return json.loads(path.read_text(encoding="utf-8"))


def load_policy(path: Path = POLICY) -> dict:
    """السياسة تُتحقَّق قبل أن تُستعمَل — ثلاث خصائص أثبتها #836 بطفراتها، تبقى مفروضة.

    وُرِّثت من الصيغة الأولى عمداً: تحسينُ النموذج لا يجوز أن يُسقِط ما أُثبِت قبله.
    """
    policy = _load(path)
    if str(policy.get("schema", "")).split("/")[0] != "sahool.gate01_policy":
        raise RuntimeError("GATE01_POLICY_SCHEMA_MISMATCH")
    # قائمةٌ فارغة ليست «لا شيء مجمَّد» — هي عقدٌ ناقص: تُفرِّغ الحارس بلا أن تُحمِّره.
    if not policy.get("frozen_paths"):
        raise RuntimeError("GATE01_POLICY_EMPTY_FROZEN_LIST")
    return policy


def canonical_patch_digest(blobs: dict[str, str]) -> str:
    """بصمة البايتات المأذونة — الوصفة مُعلَنة في التفويض نفسه فتُراجَع لا تُخمَّن."""
    canon = "".join(f"{p}\0{blobs[p]}\n" for p in sorted(blobs))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _migration_version(name: str) -> str | None:
    """رقمُ إصدار الهجرة من اسمها (``v228_worker_claim_lease.sql`` ⇒ ``v228``)."""
    match = re.match(r"(v\d+)_", name)
    return match.group(1) if match else None


def alias_candidates(frozen_path: str, root: Path = ROOT) -> list[str]:
    """ملفّاتٌ حيّةٌ **تبدو** هي المسارَ المجمَّد الغائب تحت اسمٍ آخر.

    قاعدتان، وكلتاهما مُشتقّةٌ من عطلٍ وقع لا من تخيّل:

    - **رقمُ الإصدار** — التجميدُ سمّى ``v228_phase_runtime_claim_leases.sql``
      وأُنشئ ``v228_worker_claim_lease.sql``. أرقامُ الهجرات فريدةٌ بالعقد، فالرقمُ
      هو الهويّةُ والاسمُ وصف.
    - **الاسمُ الأساسيّ في مجلّدٍ آخر** — التجميدُ سمّى ``migrations/run_migrations.sql``
      **ولم يوجد قطّ** (صفرُ التزاماتٍ في كامل التاريخ)، والمُشغِّلُ الحقيقيُّ
      ``scripts_v9/run_migrations.sql`` قائمٌ منذ أوّل التزام.
    """
    target = Path(frozen_path)
    version = _migration_version(target.name)
    out: set[str] = set()

    for candidate in root.rglob(target.name):
        rel = candidate.relative_to(root).as_posix()
        if rel != frozen_path and "node_modules" not in rel and not rel.startswith(".git/"):
            out.add(rel)

    if version is not None:
        parent = root / target.parent
        if parent.is_dir():
            for candidate in parent.glob(f"{version}_*{target.suffix}"):
                rel = candidate.relative_to(root).as_posix()
                if rel != frozen_path and "node_modules" not in rel and not rel.startswith(".git/"):
                    out.add(rel)

    return sorted(out)


def alias_escape_errors(policy: dict, root: Path = ROOT) -> list[str]:
    """مسارٌ مُجمَّدٌ غائبٌ وله نظيرٌ حيّ ⇒ **التجميدُ يحرس اسماً لا ملفّاً**.

    **العطلُ الذي وُجِد هذا الفحص لأجله، وقع مرّتين وبصنفين مختلفين:**

    ``v228`` — التجميدُ يعني «لا تُنشئه»، فأُنشئ باسمٍ آخر ودُمِج في #954 والحارسُ
    صامت. النيّةُ خُرِقت والحرفُ سليم.

    ``run_migrations.sql`` — أسوأُ صنفاً: المسارُ المجمَّد **لم يوجد قطّ**، والمُشغِّلُ
    الحقيقيُّ خارج التجميد منذ #837. أي أنّ الحراسةَ كانت **فارغةً منذ كُتِبت**،
    و#954 عدّلت المُشغِّلَ الحقيقيّ (+٣ أسطر) بلا أن يُبلِّغ شيء.

    ولا يُقرَأ هذا حكماً بأنّ الملفّ يجب أن يُجمَّد — يُقرَأ **إبلاغاً بأنّ السياسة
    تناقض الشجرة**: إمّا الاسمُ خطأٌ فيُصحَّح، أو النظيرُ دخيلٌ فيُزال. وكلاهما
    قرارُ مالكٍ لأنّه يُغيّر ما تحرسه البوّابة فعلاً.
    """
    declared_absent = set(policy.get("not_yet_in_tree") or [])
    acknowledged = policy.get("alias_mismatch_acknowledged") or {}
    errors: list[str] = []
    for frozen_path in policy.get("frozen_paths") or []:
        if (root / frozen_path).exists() or frozen_path not in declared_absent:
            continue
        aliases = alias_candidates(frozen_path, root)
        if not aliases:
            continue
        # الإقرارُ **ضيّقٌ بالبناء**: يُسمّي النظيرَ بعينه. فنظيرٌ جديد لنفس المسار
        # المجمَّد يبقى حاجباً — وإلّا صار الحقلُ بابَ تجاوزٍ دائماً بدل أن يكون
        # تسجيلَ حالةٍ معروفةٍ تنتظر حكماً. راتشِتٌ يحفظ المعروف ويمنع القادم.
        entry = acknowledged.get(frozen_path) or {}
        known = entry.get("live_alias")
        if known is not None and aliases == [known]:
            continue
        extra = [a for a in aliases if a != known]
        errors.append(
            f"{frozen_path}: مُعلَنُ الغياب ولكنّ نظيراً حيّاً موجود {extra} — "
            "التجميدُ يحرس اسماً لا ملفّاً. صحّح المسار في السياسة أو أزِل النظير."
        )
    return errors


def blob_sha(path: str, root: Path = ROOT) -> str | None:
    """بصمة المحتوى في الشجرة. ``None`` إن غاب الملفّ — والغياب لا يُقرأ تطابقاً."""
    proc = subprocess.run(
        ["git", "-C", str(root), "hash-object", path],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    out = proc.stdout.strip()
    return out if proc.returncode == 0 and out else None


def load_adjudications(directory: Path = ADJUDICATIONS) -> list[dict]:
    if not directory.is_dir():
        return []
    out = []
    for path in sorted(directory.glob("*.json")):
        out.append(_load(path))
    return out


def _authorization_errors(
    adj: dict, policy: dict, touched: set[str], blobs: dict[str, str | None]
) -> list[str]:
    """أسبابُ رفض هذا التفويض لهذا المسّ. الفارغة تعني أنّه يُغطّيه بالكامل."""
    errs: list[str] = []
    ident = adj.get("adjudication_id", "<بلا معرّف>")

    if adj.get("schema") != "sahool.gate01_adjudication/v1":
        return [f"{ident}: مخطَّطٌ غير معروف — لا يُقرأ إذناً"]
    if adj.get("gate_id") != policy.get("gate", {}).get("id"):
        errs.append(f"{ident}: تفويضٌ لبوّابةٍ أخرى")

    status = adj.get("status")
    if status != "ISSUED":
        errs.append(f"{ident}: حالته {status!r} لا ISSUED — المُستهلَك والملغى لا يُعاد استعمالهما")

    # `one_time: false` وضعٌ **غير منفَّذ** في هذا المستودع، فيُرفَض صراحةً بدل أن يُقرأ
    # ترخيصاً بإعادة الاستعمال. لا شيء هنا يُنفِّذ تفويضاً مُعاد الاستعمال: لا عدّاد
    # استعمالات ولا نطاقاً زمنيّاً ولا سقفاً — والصمت عنه كان سيجعل حقلاً إعلانيّاً
    # **يفتح باباً**، وهو بعينه الشكل الذي أعاد `GATE01-ONE-SHOT-LIFECYCLE-INCOMPLETE-01`.
    # والفرق بين الغياب والصريح مقصود: الغياب = الافتراض (لمرّةٍ واحدة)، والتصريح بـfalse
    # ادّعاءُ وضعٍ لا وجود له ⇒ فشلٌ مغلق.
    if adj.get("one_time") is False:
        errs.append(
            f"{ident}: `one_time: false` — وضعٌ غير منفَّذ: لا تفويض مُعاد الاستعمال في "
            "هذا المستودع. أصدِر تفويضاً لكلّ رقعة، أو نفِّذ الوضع بحدوده أوّلاً."
        )

    baseline = adj.get("phase0_baseline_ref") or {}
    if baseline.get("must_match_policy") is not False:
        want = (policy.get("phase0_baseline") or {}).get("commit_sha")
        if baseline.get("commit_sha") != want:
            errs.append(f"{ident}: أساسُه لا يطابق الأساس المُجمَّد في السياسة")

    allowed = adj.get("allowed_paths")
    if not isinstance(allowed, list) or not allowed:
        return errs + [f"{ident}: بلا `allowed_paths` — تفويضٌ مشوَّه"]
    extra = sorted(touched - set(allowed))
    if extra:
        errs.append(f"{ident}: مسارٌ مجمَّد خارج المأذون: {extra}")

    bindings = adj.get("bindings") or {}
    if bindings.get("require_patch_digest") is not False:
        declared_blobs = adj.get("authorized_blobs")
        if not isinstance(declared_blobs, dict) or set(declared_blobs) != set(allowed):
            errs.append(f"{ident}: `authorized_blobs` لا يغطّي المأذون بالضبط")
        else:
            if canonical_patch_digest(declared_blobs) != adj.get("authorized_patch_sha256"):
                errs.append(
                    f"{ident}: البصمة المُعلَنة لا تُشتقّ من البصمات المُعلَنة — تفويضٌ يناقض نفسه"
                )
            actual = {p: blobs.get(p) for p in allowed}
            if any(v is None for v in actual.values()):
                errs.append(f"{ident}: مسارٌ مأذون غير موجود في الشجرة")
            elif actual != declared_blobs:
                errs.append(
                    f"{ident}: بايتاتُ الشجرة تخالف المأذون — التفويض على بايتاتٍ بعينها، "
                    "وتغيُّر محرفٍ يُبطِله"
                )

    if bindings.get("require_exact_head_sha") is True:
        head = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        ).stdout.strip()
        if head != adj.get("head_sha"):
            errs.append(f"{ident}: الرأس تغيّر عمّا أُذِن به")

    return errs


def evaluate(
    changed: list[str], policy: dict, adjudications: list[dict], blobs: dict[str, str | None]
):
    """يُرجِع (أخطاء، معرّف التفويض المُستعمَل أو None). فارغةٌ تعني PASS."""
    frozen = set(policy.get("frozen_paths") or [])
    touched = {p for p in changed if p in frozen}
    if not touched:
        return [], None

    gate = policy.get("gate") or {}
    if str(gate.get("state", "")).strip().upper() == "OPEN":
        return [], None

    if not adjudications:
        return [
            f"مسارٌ مجمَّد خلف {gate.get('gap_id')} مُعدَّل بلا تفويض: {sorted(touched)} — "
            "البوّابة مغلقة. أصدِر تفويضاً مقيَّداً بقرار مالك، أو أرجِع الملفّ."
        ], None

    reasons: list[str] = []
    for adj in adjudications:
        errs = _authorization_errors(adj, policy, touched, blobs)
        if not errs:
            return [], adj.get("adjudication_id")
        reasons.extend(errs)
    return (
        [f"مسارٌ مجمَّد مُعدَّل ولا تفويض يُغطّيه: {sorted(touched)}"] + reasons,
        None,
    )


def stale_authorization_errors(
    adjudications: list[dict], touched: set[str], blobs: dict[str, str | None]
) -> list[str]:
    """تفويضٌ `ISSUED` هبطت بايتاتُه بالفعل ⇒ استُهلِك ولم يُختَم.

    **الفجوة المقيسة `GATE01-ONE-SHOT-LIFECYCLE-INCOMPLETE-01`:** حقل `one_time`
    يَعِد بأنّ التفويض المُستعمَل لا يُستعمَل ثانيةً، و`_authorization_errors` يفرض
    `status == "ISSUED"` — لكن **لا شيء يُحوِّل `ISSUED` إلى `CONSUMED` بعد الدمج**.
    فبقي تفويض `#837` صالحاً بعد هبوط رقعته، وشُغِّلت `evaluate()` عليه فأعطت PASS.

    **ولماذا ليس «كلّ ISSUED بايتاتُه مطابقة» مخالفةً:** أثناء الـPR المأذونة نفسها
    تكون البايتات مطابقةً للشجرة — فذلك هو الاستعمال المشروع. والمُميِّز أن يكون
    الـdiff الحاليّ **لا يلمس** المسارات المأذونة: عندها التطابق يعني أنّها هبطت
    سلفاً، لا أنّها تُستعمَل الآن.

    **ولماذا لا يُسأل GitHub «أمدموجةٌ الـPR؟»:** لأنّ عقد هذا المستودع أنّ حالة
    GitHub لا تدخل أداةً — تُقاس في الوظيفة ويُحكَم في الحارس. وهذا البديل يُشتقّ من
    **الشجرة وحدها**، فيعمل محلّيّاً بلا شبكة ويلتقط الحالة نفسها.

    **والحارس يبقى للقراءة فقط:** يكشف ولا يختم. الختم إجراءٌ منفصل بعد الدمج —
    فحارسٌ يكتب أثناء CI يصير طرفاً في القرار الذي يحكم فيه.

    **ولا يُستثنى `one_time: false` هنا** رغم أنّ اسم الفجوة يذكر «لمرّةٍ واحدة»: هذا
    الوضع **غير منفَّذ** أصلاً، و`_authorization_errors` يرفضه صراحةً. فاستثناؤه هنا
    كان سيجعل حقلاً إعلانيّاً يُسكِت فحصَ دورة الحياة بلا أن يمنحه أحد ذلك — أي
    بابَ تجاوزٍ ذاتيَّ الخدمة يُعيد الفجوة من حيث أُغلِقت.
    """
    errs: list[str] = []
    for adj in adjudications:
        if adj.get("status") != "ISSUED":
            continue
        allowed = adj.get("allowed_paths")
        declared = adj.get("authorized_blobs")
        if not isinstance(allowed, list) or not isinstance(declared, dict):
            continue
        if set(allowed) & touched:
            continue  # يُستعمَل في هذا التغيير — استعمالٌ مشروع لا بقاءٌ بائت
        if any(blobs.get(p) is None for p in allowed):
            continue  # مسارٌ غائب ⇒ لم يهبط
        if {p: blobs.get(p) for p in allowed} != declared:
            continue  # الشجرة تخالف المأذون ⇒ لم يهبط بعد
        ident = adj.get("adjudication_id", "<بلا معرّف>")
        errs.append(
            f"{ident}: تفويضٌ `ISSUED` وبايتاتُه المأذونة **هبطت بالفعل** في الشجرة "
            f"[pr={adj.get('pr')}] — استُهلِك ولم يُختَم. اختمه `CONSUMED` مع "
            "`merge_sha`، وإلّا بقي إذناً حيّاً يُعيد رقعةً سبق الإذن بها "
            "(GATE01-ONE-SHOT-LIFECYCLE-INCOMPLETE-01)."
        )
    return errs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="حارس GATE-01 — تفويضٌ مقيَّد يُستهلَك")
    parser.add_argument("--stdin", action="store_true", help="اقرأ المسارات المُغيَّرة من stdin")
    parser.add_argument("--policy", default=str(POLICY))
    parser.add_argument("--adjudications", default=str(ADJUDICATIONS))
    args = parser.parse_args(argv)

    changed = (
        [line.strip() for line in sys.stdin.read().splitlines() if line.strip()]
        if args.stdin
        else []
    )
    policy = load_policy(Path(args.policy))
    adjudications = load_adjudications(Path(args.adjudications))
    blobs = {p: blob_sha(p) for p in (policy.get("frozen_paths") or [])}

    errors, used = evaluate(changed, policy, adjudications, blobs)
    # فحصُ دورة الحياة يجري **دائماً**، حتّى حين لا يُمَسّ مجمَّد: تفويضٌ بائت لا
    # يُكتشَف بالمسّ بل بمرور الزمن عليه، فلو رُبِط بالمسّ لبقي صامتاً إلى أن
    # يستعمله أحد — وهو الأوان الذي وُجِد ليسبقه.
    frozen = set(policy.get("frozen_paths") or [])
    frozen_touched = {p for p in changed if p in frozen}
    errors = list(errors) + stale_authorization_errors(adjudications, frozen_touched, blobs)
    # فحصُ النظائر يجري **دائماً** كفحصِ دورة الحياة: تجميدٌ يحرس اسماً لا ملفّاً لا
    # يُكتشَف بالمسّ — يُكتشَف بوجود النظير. ولو رُبِط بالمسّ لبقي صامتاً إلى أن يمسّه
    # أحدٌ، وهو الأوان الذي وُجِد ليسبقه.
    errors = errors + alias_escape_errors(policy)
    if errors:
        print("gate01_frozen_path_guard_failed")
        for e in errors:
            print(f"- {e}")
        return 1
    print(f"gate01_frozen_path_guard_ok{f' (تفويض: {used})' if used else ''}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
