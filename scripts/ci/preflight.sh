#!/usr/bin/env bash
# ============================================================================
# preflight.sh — يُعيد إنتاج بوّابات CI الحاجبة محلّيّاً قبل الدفع
# ============================================================================
# §٢ من `docs/runbooks/CI_GATES_AND_PRE_PUSH_PROTOCOL.md` كانت كتلة تُنسَخ باليد.
# هذا هو نفسه سكربتاً مُلتزَماً: ما يُنسَخ يُنسَى نصفه، وما يُلتزَم يُشغَّل كاملاً.
#
#   bash scripts/ci/preflight.sh --fast   # ~٣٠ث  — لِنت وحرّاس ثابتة، بلا جناح
#   bash scripts/ci/preflight.sh          # ~٧د   — يضيف الجناحين والمكنسة
#   bash scripts/ci/preflight.sh --full   # ~١٢د  — يضيف الأمن ولغة الآلة
#   bash scripts/ci/preflight.sh --fix    # يُعيد التوليد بدل الفحص، ثمّ يُكمِل
#   bash scripts/ci/preflight.sh --pr-body-file body.md
#                                         # يُشغّل بوّابة الحجب ذاتها على متن الـPR
#   bash scripts/ci/preflight.sh --no-fetch  # لا تجلب origin/main عند حلّ الأساس
#
# ── صفته: أداة تطوير محلّيّة (أو pre-push اختياريّ) ─────────────────────────
# **ليست بوّابة CI ولا مصدر قرار.** وقيدٌ يتبع ذلك ويُفرَض باختبار عقد: لا تقرأ
# **حالة GitHub** إطلاقاً — لا سرد PRs، ولا حالة اخضرار، ولا ترتيب دمج. تلك أحكام
# متغيّرة موضعها الدليل التشغيليّ (§٣.٢١) حيث تحمل تاريخ تحقّق وعقد صيانة. ما هنا
# **حقائق محلّيّة قابلة لإعادة الإنتاج** وحدها.
#
# ── ما لا يفعله هذا السكربت (اقرأه قبل أن تثق بأخضره) ──────────────────────
# الأخضر هنا يعني «ما قِيس مرّ»، لا «CI ستخضرّ». §٣.١٧ تقيس أنّ workflows تستدعي
# **٢٠٩** بوّابة و§٢ تغطّي **٧٠** منها. الباقي عقود نطاق (raster · weather · edge ·
# mobile · vegetation …) تُسقِطها تغييرات نطاقها وحدها، ولا يمكن لسكربت واحد أن
# يخمّن نطاقك. اشتقّ بوّاباتك من مساراتك المُعدَّلة — والقسم الأخير هنا يطبع
# القدرات المتأثّرة ليساعدك على ذلك.
# ============================================================================
set -uo pipefail

# الرفض على الأرشيف مُغلَق عند الفشل ومقصود: أرشيف بلا `.git` يجعل المولّدات تسقط على
# البيان الموقَّع فتُبلِغ **أخضر كاذباً** — مقيس، وحزمة كاملة بُنيت هكذا ولم تصلح للدمج.
ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "✗ لست داخل شجرة عمل git — التشغيل على أرشيف يُنتِج أخضر كاذباً" >&2; exit 1
}
cd "$ROOT" || exit 1
[ -d .git ] || [ -f .git ] || {
  echo "✗ بيانات git غير متاحة — التشغيل على أرشيف يُنتِج أخضر كاذباً" >&2; exit 1
}

TIER=default
FIX=0
FETCH=1
PR_BODY_FILE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --fast) TIER=fast ;;
    --full) TIER=full ;;
    --fix)  FIX=1 ;;
    --no-fetch) FETCH=0 ;;
    --pr-body-file)
      shift; [ $# -gt 0 ] || { echo "✗ --pr-body-file يحتاج قيمة" >&2; exit 2; }
      PR_BODY_FILE="$1" ;;
    -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
    *) echo "✗ راية غير معروفة: $1" >&2; exit 2 ;;
  esac
  shift
done

BASE="${BASE:-origin/main}"
CONTRACT="docs/architecture/preflight_required.json"
failures=0
skipped=0

# رموز الخروج تُقرأ بالصيغة التي أثبتت صحّتها في §٢، لا بـ`&&/||`:
#   `"$@" || rc=$?` يلتقط الحالة الحقيقيّة ويحمي من `set -e`
#   `if/fi` + `return 0` صريح، فلا تصير قيمة آخر شرط قيمةَ إرجاع الدالّة
#   (الصيغة `[ $rc -ne 0 ] && echo …` تُعيد ١ عند النجاح — عطل مقيس هنا)
# ④ بوّابة اختفى سكربتها ليست بوّابة مرّت. الصيغة الساذجة `run "x" python3 y.py`
# تُبلِّغ فشلاً عاديّاً عند حذف `y.py`، فيُقرأ خطأً برمجيّاً لا **تقلّصاً في التغطية**.
# يُفحَص الوجود أوّلاً ويُسمّى الغياب باسمه.
require_file() {
  if [ ! -f "$1" ]; then
    failures=$((failures + 1))
    echo "── $2"
    echo "   ✗ سكربت بوّابة مفقود: $1 — التغطية تقلّصت، لا اختبار فشل"
    return 1
  fi
  return 0
}

run() {
  local label="$1"; shift
  printf '── %s\n' "$label"
  local rc=0
  "$@" >/tmp/preflight_step.log 2>&1 || rc=$?
  if [ "$rc" -ne 0 ]; then
    failures=$((failures + 1))
    echo "   ✗ فشل ($rc)"
    tail -15 /tmp/preflight_step.log | sed 's/^/     /'
  else
    echo "   ✓"
  fi
  return 0
}

need() {  # يتخطّى بصوت عالٍ بدل أن يمرّ صامتاً — التخطّي الصامت يُقرأ نجاحاً
  if command -v "$1" >/dev/null 2>&1; then return 0; fi
  echo "── $2"
  echo "   ⊘ متخطّاة: '$1' غير مثبَّت — هذه البوّابة **لم تُقَس**"
  skipped=$((skipped + 1))
  return 1
}

echo "═══ preflight ($TIER) — أساس المقارنة: $BASE ═══"

# ── ٠) حداثة الفرع — أوّلاً عمداً ──────────────────────────────────────────
# الترتيب قرار لا تفضيل: التوليد على قاعدة بائتة يُعاد دفع ثمنه كاملاً بعد الدمج،
# فمعرفة التأخّر **قبل** إنفاق دقائق المكنسة والجناحين توفّرها. المقايضة معلومة: لِنتٌ
# أحمر في ثانيتين يُعرَف بعد هذه الخطوة لا قبلها — ولذلك بقيت `--fast` بلا مكنسة
# لحلقة اللِّنت السريعة.
# ③ سلّم بدائل صريح: الأساس قد لا يكون `origin/main` في نسخة بلا remote.
echo "── ٠) قاعدة المقارنة وحداثة الفرع"
[ "$FETCH" = 1 ] && git fetch origin main -q 2>/dev/null || true
for candidate in "$BASE" origin/main main; do
  if git rev-parse --verify "$candidate^{commit}" >/dev/null 2>&1; then BASE="$candidate"; break; fi
done
if git rev-parse --verify "$BASE^{commit}" >/dev/null 2>&1; then
  merge_base=$(git merge-base "$BASE" HEAD 2>/dev/null || echo "")
  behind=$(git rev-list --count "HEAD..$BASE" 2>/dev/null || echo "?")
  echo "   ✓ base=$BASE merge-base=$(printf '%.8s' "$merge_base") behind=$behind"
  if [ "$behind" != "0" ]; then
    echo "   ⚠ الفرع متأخّر $behind التزاماً — التوليد على قاعدة بائتة يُعاد دفع ثمنه"
    echo "     ادمج **ثمّ أعِد التوليد**؛ وتعارضات المصنوعات: خُذ main وأعِد التوليد لا يدويّاً"
  fi
else
  echo "   ⊘ متخطّاة: لا مرجع قاعدة متاح — طبقة الأثر **لم تُقَس**"
  skipped=$((skipped + 1))
fi

# ── العقد: ما يجب أن يكون موجوداً قبل أن يُعتَدّ بأخضر هذا السكربت ─────────
# القائمة بيانات في `docs/architecture/preflight_required.json`، لا سطور هنا:
# قائمة مدفونة في أداة تبيت بصمت — الصنف الذي أسقط جدول `SENSITIVE` والمحرّك الثاني
# لأثر القدرات في هذه الجلسة نفسها. وغياب عنصر مُعلَن **تقلّص تغطية** لا خطأ تشغيل.
echo "── ٠أ) عقد المتطلّبات ($CONTRACT)"
if [ ! -f "$CONTRACT" ]; then
  failures=$((failures + 1))
  echo "   ✗ عقد المتطلّبات مفقود — لا يُعرَف ما الذي يجب أن يوجد"
else
  missing=$(python3 - "$CONTRACT" <<'PY'
import json, sys
from pathlib import Path
data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
gone = [p for key in ("required_tests", "required_scripts")
        for p in data.get(key, []) if not Path(p).exists()]
print("\n".join(gone))
PY
)
  if [ -n "$missing" ]; then
    failures=$((failures + 1))
    echo "   ✗ مسارات مُعلَنة في العقد وغير موجودة — التغطية تقلّصت:"
    echo "$missing" | sed 's/^/     /'
  else
    echo "   ✓ كلّ ما يُعلِنه العقد موجود"
  fi
fi

# ── ٠ب) الشجرة والفهرس ────────────────────────────────────────────────────
# المولّدات تُعدّد `git ls-files` (المتعقَّب وحده). ملفّ جديد لم يُضَف غير مرئيّ لها،
# فتخرج المصنوعة خاليةً منه ثمّ يظهر الانحراف في أوّل تشغيل بعد الالتزام (§٣.١).
echo "── ٠ب) الفهرس قبل التوليد"
# «غير متعقَّب» ليس كلّ ما يُخفي انحرافاً: تعديل غير مُدرَج على ملفّ **متعقَّب** يُقاس
# أيضاً على حالة مختلفة عمّا سيُدفَع. الحالتان تُبلَّغان، لا واحدة منهما.
untracked=$(git ls-files --others --exclude-standard | wc -l | tr -d ' ')
if [ "$untracked" -gt 0 ]; then
  echo "   ⚠ $untracked ملفّ غير متعقَّب — المولّدات تُعدّد git ls-files فلا تراها"
  git ls-files --others --exclude-standard | head -5 | sed 's/^/     /'
else
  echo "   ✓ لا ملفّات غير متعقَّبة"
fi
unstaged=$(git diff --name-only | wc -l | tr -d ' ')
staged=$(git diff --cached --name-only | wc -l | tr -d ' ')
if [ "$unstaged" -gt 0 ]; then
  echo "   ⚠ $unstaged تعديلاً غير مُدرَج — ما يُقاس ليس ما سيُدفَع. نفّذ: git add -A"
elif [ "$staged" -gt 0 ]; then
  echo "   ✓ $staged تغييراً مُدرَجاً، ولا تعديل خارج الفهرس"
else
  echo "   ✓ الشجرة والفهرس نظيفان"
fi

# ── ١) اللِّنت والتنسيق — بوّابة Lint & Format، كامل الشجرة ────────────────
if need ruff "١) ruff"; then
  run "١أ) ruff check ."          ruff check .
  if [ "$FIX" = 1 ]; then
    run "١ب) ruff format ."       ruff format .
  else
    run "١ب) ruff format --check ." ruff format --check .
  fi
fi

# ── ٢) حارسا تعارض الدمج — لا يغني أحدهما عن الآخر ────────────────────────
require_file scripts/ci/no_merge_conflict_markers_guard.py "٢ب) no_merge_conflict_markers" && run "٢ب) no_merge_conflict_markers" python3 scripts/ci/no_merge_conflict_markers_guard.py

# ── ٣) أساس الادّعاءات وحارس الطفرات ──────────────────────────────────────
require_file scripts/ci/claim_base_guard.py "٣أ) claim_base_guard" && run "٣أ) claim_base_guard"        python3 scripts/ci/claim_base_guard.py
run "٣ب) guard_mutation (ساكن)"   python3 scripts/ci/guard_mutation_guard.py

# ── ٤) عقود compose/البيئة — أيّ متغيّر جديد يُعلَن في .env.example ─────────
run "٤أ) compose_env_contract"    python3 scripts/ci/compose_env_contract_gate.py
run "٤ب) env_compose_drift"       python3 scripts/ci/env_compose_drift_guard.py --check
run "٤ج) compose_runtime_target"  python3 scripts/ci/compose_runtime_target_resolver.py --check

# ── ٥) تسجيل الاختبارات وعلاماتها ─────────────────────────────────────────
run "٥أ) arch_test_ci_coverage"   python3 scripts/ci/arch_test_ci_coverage_guard.py
run "٥ب) marker_coverage"         python3 scripts/ci/test_marker_coverage_guard.py --check

# ── ٦) حرّاس الدماغ — على مدى الـPR لا على الشجرة ─────────────────────────
run "٦أ) brain_deferral"          python3 scripts/ci/brain_deferral_registry_guard.py
if git rev-parse --verify "$BASE" >/dev/null 2>&1; then
  run "٦ب) brain_state_transition" python3 scripts/ci/brain_state_transition_guard.py --base "$BASE" --head HEAD
  run "٦ج) brain_commit_claim"     python3 scripts/ci/brain_commit_claim_guard.py --base "$BASE" --head HEAD
else
  echo "── ٦ب/٦ج) حرّاس مدى الـPR"
  echo "   ⊘ متخطّاة: '$BASE' غير موجود — **لم تُقَس**"
  skipped=$((skipped + 2))
fi

if [ "$TIER" = fast ]; then
  echo
  echo "═══ fast: إخفاقات=$failures · متخطّاة=$skipped ═══"
  echo "الجناحان والمكنسة **لم يُشغَّلا**. لا تدفع على هذا وحده."
  [ "$failures" -eq 0 ] || exit 1
  exit 0
fi

# ── ٧) المصنوعات المولَّدة — بعد الفهرسة لا قبلها ─────────────────────────
# مداها **٤٧ خطوة على ١٨ workflow**، والمولّدات تبصم مخرجات بعضها: إصلاح واحد
# يكشف التالي. لذلك مكنسة واحدة تُكرِّر حتّى الثبات، لا مولّد مُنتقى باليد.
if require_file scripts/ci/verify_all_generated.py "٧) verify_all_generated"; then
  if [ "$FIX" = 1 ]; then
    git add -A
    run "٧أ) verify_all_generated --fix" python3 scripts/ci/verify_all_generated.py --fix
    git add -A
    # الفحص **بعد** الإصلاح ليس تزيّداً: رمز خروج `--fix` يقول «انتهيتُ» لا «تقاربت»،
    # و§٣.١٦ تقيس أنّ بعض خطوات `--check` تكتب أثناء الفحص. فالتقارب يُثبَت بفحصٍ
    # تالٍ أو لا يُثبَت.
    run "٧ب) verify_all_generated --check (إثبات التقارب)" \
      python3 scripts/ci/verify_all_generated.py --check
  else
    # `--check` صريحاً لا اتّكالاً على الافتراضيّ: مُستدعٍ بلا راية يتغيّر معناه لو
    # تغيّر افتراض الأداة، بلا تعديل سطر عنده.
    run "٧) verify_all_generated --check" python3 scripts/ci/verify_all_generated.py --check
  fi
fi

# ── ٨) الجناحان — الأغلى، وآخرهما عمداً ───────────────────────────────────
# `-m unit` هو بوّابة *Unit Tests*؛ و`tests/` وظيفة حاجبة **مستقلّة** لا يشملها
# `-m unit` (§٢/٧ب) — أُغفِلت من الكتلة الأصليّة حتّى أسقطت بناءً.
run "٨أ) pytest -m unit"  python3 -m pytest -q -m unit
run "٨ب) pytest tests/"   python3 -m pytest -q tests/

if [ "$TIER" = full ]; then
  # ── ٩) الأمن — bandit يحجب على HIGH وحده؛ الباقي إرشاديّ ────────────────
  if need bandit "٩أ) bandit"; then
    run "٩أ) bandit (HIGH يحجب)" bandit -r services/ bots/ agents/ --severity-level high -q
  fi
  # pip-audit يحجب على ١٩ ملفّ متطلّبات، والاستثناء الموثَّق راية إلزاميّة وإلّا
  # ظهرت نتيجة حمراء كاذبة (ecdsa · WONTFIX عند صانعيه · مسارنا يوقّع عبر cryptography).
  if need pip-audit "٩ب) pip-audit"; then
    run "٩ب) pip-audit (المسار الحرج)" \
      pip-audit -r requirements_real.txt --ignore-vuln PYSEC-2026-1325
  fi
  # ── ١٠) المتّجه الذي يخفيه Linux: ترميز لغة الآلة (§٣.١٠) ───────────────
  run "١٠) pytest -m unit تحت لغة C" \
    env LC_ALL=C PYTHONUTF8=0 python3 -m pytest -q -m unit
fi

# ── ١١) القدرات المتأثّرة — لا جدول مُصلَّب ────────────────────────────────
# الأداة تقرأ المحرّك نفسه الذي تقرؤه البوّابة الحاجبة (حارس التكافؤ في
# `tests_v9/test_capability_impact_parity.py` يمنعهما من التباعد)، فجوابها هو
# جوابها. جدولٌ يُصان بيد كان سيبيت؛ الأداة لا تبيت.
# ② حين يُمرَّر متن الـPR تُشغَّل **البوّابة الحاجبة ذاتها** فتُعاد إنتاج قرار الحجب،
# لا اقتراحٌ يُشبهه. الاقتراح يساعد على الكتابة؛ البوّابة وحدها تقول هل تمرّ.
if [ -n "$PR_BODY_FILE" ]; then
  echo "── ١١أ) بوّابة Capability-Impact الحاجبة على متن الـPR"
  if [ ! -f "$PR_BODY_FILE" ]; then
    failures=$((failures + 1))
    echo "   ✗ ملفّ المتن غير موجود: $PR_BODY_FILE"
  else
    base_sha=$(git merge-base "$BASE" HEAD 2>/dev/null || echo "")
    if [ -n "$base_sha" ]; then
      run "١١أ) pr_capability_impact_gate --pr-body-file" \
        python3 scripts/ci/pr_capability_impact_gate.py \
          --base "$base_sha" --head "$(git rev-parse HEAD)" \
          --pr-body-file "$PR_BODY_FILE"
    else
      echo "   ⊘ متخطّاة: تعذّر حلّ merge-base مع $BASE — **لم تُقَس**"
      skipped=$((skipped + 1))
    fi
  fi
fi

echo "── ١١ب) Capability-Impact المقترح لمتن الـPR"
changed=$(git diff --name-only "$BASE...HEAD" 2>/dev/null || true)
if [ -n "$changed" ]; then
  # shellcheck disable=SC2086
  direct=$(python3 scripts/ci/capability_impact.py --json $changed 2>/dev/null \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print("ALL" if d["governance_wide"] else ",".join(d["direct"]))' 2>/dev/null)
  if [ -n "$direct" ]; then
    echo "   Capability-Impact: $direct"
    echo "   تذكير: البوّابة تعمل على pull_request بلا types ⇒ لا تستمع لـ edited."
    echo "   تعديل المتن **لا** يُعيد تشغيلها، وrerun يعيد استخدام حمولة الحدث القديمة."
    echo "   الطريق الوحيد لالتقاط متن جديد: دفعة تُطلِق synchronize."
  else
    echo "   Capability-Impact: NONE  (لا مسار من مساراتك يمسّ قدرة مُسجَّلة)"
  fi
else
  # «لا فرق» هنا لا يعني «لا قدرة متأثّرة» — يعني **لم يُشتقّ شيء**، وأشيع سببه أنّ
  # التشغيل سبق الالتزام. وهذا الفرع كان صامتاً فمرّ ضمن «متخطّاة: 0»، ودُفِع متنٌ
  # بلا سطر `Capability-Impact` فحجبت `capability-registry` جولةً كاملة (#814).
  # والفرع الآخر أعلاه يحمل التحذير كلّه؛ الصمت هنا كان الثقب.
  echo "   ⊘ متخطّاة: لا فرق مقابل $BASE — **لم يُشتقّ سطر Capability-Impact**"
  echo "     إن لم تكن قد التزمتَ بعد فهذا متوقَّع: التزِم ثمّ أعِد هذه الخطوة وحدها،"
  echo "     ولا تدفع متناً بلا السطر. البوّابة تعمل على pull_request بلا types ⇒ لا"
  echo "     تستمع لـ edited، فتعديل المتن بعد الدفع **لا** يُعيد تشغيلها."
  echo "     اشتقّه بـ: python3 scripts/ci/pr_capability_impact_gate.py --base $BASE --head HEAD"
  skipped=$((skipped + 1))
fi

echo
echo "═══ إخفاقات: $failures · متخطّاة: $skipped ═══"
if [ "$skipped" -gt 0 ]; then
  echo "⚠ $skipped بوّابة لم تُقَس — «لم أنظر» ليس «لا يوجد»."
fi
if [ "$failures" -eq 0 ]; then
  echo "أخضر على ما قِيس. §٣.١٧: workflows تستدعي ٢٠٩ بوّابة وهذا يغطّي ٧٠."
  echo "اشتقّ عقود نطاقك من مساراتك المُعدَّلة قبل الدفع."
else
  echo "أصلِح ما فوق. كلّ فشل هنا كان سيكلّف جولة CI كاملة."
fi
[ "$failures" -eq 0 ]
