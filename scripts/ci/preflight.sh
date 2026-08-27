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
# **٢٦١** بوّابة و§٢ تغطّي **٨٦** منها (تسميةً مباشرة أو عبر المكنسة). الباقي عقود
# نطاق (raster · weather · edge ·
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
  # الحرّاس يطبعون بالعربيّة، وطرفيّة Windows الافتراضيّة `cp1252` لا تُرمِّزها ⇒
  # `UnicodeEncodeError` يُسقِط الحارس **قبل أن يقيس شيئاً**، فيُقرأ فشلاً وهو عطل
  # طرفيّة. المقيس: سبعة من أربعة عشر حارساً ثابتاً سقطت هكذا على Windows/Python 3.13،
  # وصفرٌ على Linux؛ وأُعيد إنتاجه بـ`PYTHONIOENCODING=cp1252` ⇒ نفس الاستثناء بالحرف.
  #
  # **ويُضبَط هنا لا بـ`export` عامّ، وهذا مقيس لا احتياط:** التصدير العامّ يُورَّث إلى
  # خطوة ١٠ (`LC_ALL=C PYTHONUTF8=0`) وهي موجودة **لتقيس متّجه الترميز نفسه**، فيُبطِل
  # غرضها. قيس ذلك مباشرةً: `test_new_assertionless_test_is_rejected` يمرّ بلا المتغيّر
  # ويسقط معه. فالنطاق جزءٌ من الإصلاح لا تفصيلاً فيه. CI-GUARDS-CRASH-ON-NON-UTF8-CONSOLE-01
  PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}" "$@" >/tmp/preflight_step.log 2>&1 || rc=$?
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

# ── ٠ج) مِسبار اختبار تسرّب — **بعد ٠ب مباشرةً عمداً** ─────────────────────
# TEST-PROBE-LEAKS-INTO-THE-TREE-01 وقع **مرّتين**، والثانية بعد أن كُتِب حارسه:
# جلسة محلّيّة قوطعت أثناء `test_api_versioning_policy_guard` (يحقن مساراً غير مُصنَّف
# ويُعيد التوليد عمداً ثمّ يستعيد في `finally`؛ و`finally` لا ينجو من مقاطعة)، فبقي
# `_probe_unadjudicated_route.py` والجرود المولَّدة منحرفة. ثمّ **قال هذا السكربت
# «إخفاقات=0»** — لأنّ ٠ب تطبع «⚠ ملفّ غير متعقَّب» بلا أن تسمّي أيّهما ولا علاجه —
# فقُرِئ أخضره أخضرَ، ثمّ ظهر العطل بعد ذلك **أحد عشر إخفاقاً** في `pytest -m unit`
# على جرودٍ مشتقّة من المسارات، فأُنفِق التشخيص على أعراضٍ لا على السبب.
#
# والحارس قائم ويحجب في CI (`ci.yml:536`) ويطبع السبب والعلاج بسطر واحد — لكنّه
# **لم يكن يُستدعى محلّيّاً قطّ**. فالفجوة لم تكن في الحارس بل في أنّ الشجرة تُدفَع
# على أخضرِ أداةٍ لا تسأله. وهو Python صرف، أقلّ من ثانية، ولا يحتاج خدمة.
require_file scripts/ci/probe_leak_guard.py "٠ج) probe_leak" && run "٠ج) probe_leak" python3 scripts/ci/probe_leak_guard.py

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

# ── ٢أ) نسخٌ احتياطيّةٌ يدويّةٌ متعقَّبة — في الطبقة الأرخص عمداً ────────────
# DEAD-FILES-TRACKED-AS-IF-THEY-WERE-SOURCE-01: `git ls-files` + مطابقةُ لواحق، أقلّ
# من ثانية. وموضعُه هنا لا في `--full` لأنّ الصنفَ يدخل الشجرةَ لحظةَ `git add -A`
# — وهي الخطوةُ التي يوصي بها هذا الملفُّ نفسُه قبل التوليد.
require_file scripts/ci/no_manual_backup_files_guard.py "٢أ) no_manual_backup_files" && run "٢أ) no_manual_backup_files" python3 scripts/ci/no_manual_backup_files_guard.py

# ── ٢ز) عقودُ المسارات العابرة — فحصٌ ساكنٌ في ثوانٍ ────────────────────────
# CONTRACT-WHOSE-TWO-ENDS-ARE-TESTED-APART-01: يقابل ما يطلبه كلُّ عميلٍ في المنصّة
# بما تُعلنه خدمتُه. لا يقيس أنّ الخدمة تستجيب — بل أنّ المسارَ مُعلَنٌ فيها،
# وهو بالضبط الصنفُ الذي أفلت من اختبارَي الطرفين معاً.
require_file scripts/ci/cross_service_path_contract_guard.py "٢ز) cross_service_path_contract" && run "٢ز) cross_service_path_contract" python3 scripts/ci/cross_service_path_contract_guard.py

# ── ٢ج) محارف الاتّجاه الخفيّة — في الملفّ **الافتراضيّ** عمداً ─────────────
# BIDI-CONTROL-CHAR-PASSED-THE-DEFAULT-PREFLIGHT-01: محرف RLM في docstring عربيّ أسقط
# *Security Scan* بـB613، على رأسٍ أُعلِن أخضر — وفاتَ لأنّ bandit في `--full` وحده
# والدفعُ كان على الافتراضيّ. الحادثة كلّها «اختيارُ ملفٍّ أرخص ثمّ قراءةُ أخضره
# أخضرَ CI»، فموضعُ العلاج هو الملفّ الأرخص نفسه. Python صرف، أقلّ من ثانيتين.
require_file scripts/ci/bidi_control_char_guard.py "٢ج) bidi_control_char" && run "٢ج) bidi_control_char" python3 scripts/ci/bidi_control_char_guard.py

# ── ٢د) مسارُ تجهيزةٍ غير ASCII — نفس صنف ٢ج، ومقيسٌ **أربع مرّات** ────────
# NON-ASCII-TEST-FIXTURE-PATH-BREAKS-C-LOCALE-01 وقع في #820 ثمّ #824، فكُتِب له حارس
# ثمّ وقع **في الحارس نفسه**، ثمّ وقع رابعةً في `test_resilient_apt_install.py:224`
# باللفظ ذاته حرفيّاً (`لا-وجود-له.<لاحقة>` لتأكيدٍ عن ملفٍّ غائب — والعربيّة فيه
# زينةٌ لا خاصّيّة).
#
# والحارس قائم ويحجب. لكنّه اختبار pytest لا سكربت، فلا يعمل إلّا داخل ٨أ — أي في
# جناحٍ مقيسُه **١١د٢٧ث** خارج الطبقة السريعة. فمَن دفع على أخضر `--fast` دفع على
# أداةٍ لم تسأله: جولة CI كاملة (**٥٣ دقيقة** حتّى الحمرة) لسؤالٍ يُقاس هنا في
# **١٫٦ث**. وهو حرفيّاً صنف ٢ج فوقه بسطر: حارسٌ رخيص محبوسٌ في طبقةٍ غالية.
run "٢د) non_ascii_fixture_path" python3 -m pytest -q tests_v9/test_non_ascii_fixture_path_guard.py

# ── ٢ﻫ) مفتاحٌ مكرَّر في JSON — نصٌّ صحيحٌ يُحمَّل غيرَ ما كُتِب ────────────────
# MUT-REGISTRY-DUPLICATE-KEY-SHADOWS-A-BLOCK-01: `json.load` آخِريُّ الترجيح، فكتلةٌ
# ثانيةٌ لمفتاحٍ قائم تطرح الأولى بلا كلمة. ومقيسٌ على `a1f5da7f`: سجلُّ الطفرات نفسه
# حمل مفتاحين مكرّرين تحت `behavioural`. وموضعُه هنا لا في طبقةٍ أغلى لأنّه يقرأ
# ٢٣٣ ملفّاً في أقلّ من ثانية، ولأنّ الوثيقةَ التي أصابها العطلُ هي التي تُشغَّل بها
# البوّابة نفسها — عمًى فيها يُسكِت حرّاساً أخرى قبل أن يُسكِت نفسه.
require_file scripts/ci/json_duplicate_key_guard.py "٢ﻫ) json_duplicate_key" \
  && run "٢ﻫ) json_duplicate_key" python3 scripts/ci/json_duplicate_key_guard.py

# ── ٢و) فكُّ ترميز النصّ بلغة الآلة — الصنفُ نفسُه في الطبقة نفسها ─────────────
# GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01. الحارس قائمٌ ويحجب، لكنّه
# اختبارُ pytest فلا يعمل إلّا في ٨أ — جناحٌ مقيسُه **٣٦٢ث**. وهو حرفيّاً حُجّة ٢د
# فوقه بسطرين، ومقيسٌ في هذه الجلسة لا مُفترَض: على #886 مرّ `--fast` **أخضر** على
# شجرةٍ حمّرها الجناحُ الكامل — أربعةُ مواضع `subprocess(text=True)` بلا `encoding`
# في ملفّ اختبارٍ متبنًّى. والأدهى أنّ الصنف نفسه كان قد أُصلِح على #884 **في هذه
# الجلسة** ثمّ أُعيد بتبنّي شيفرةٍ واردة: القراءةُ لم تمسكه، والقياسُ أمسكه بعد ٦
# دقائق كان يكفيها **٤٫٦ث** هنا.
#
# **وحدُّه مُعلَنٌ لا مُفترَض:** يُشغَّل الاختبارُ الحاجب وحده (٤٫٦ث) لا الملفّ كلُّه
# (١٧٫٧ث). فحارسا التملّص — «الأساس لا ينمو» و«ملفٌّ مُؤسَّس لا يُضيف مخالفةً» —
# يبقيان في ٨أ عن قصد: **المخالفةُ خفيّةٌ في المراجعة والمهربُ ظاهرٌ فيها**، فنموُّ
# الأساس يُرى في الـdiff بينما قراءةٌ بلا ترميز في ملفٍّ جديد لا تُرى إلّا بالمسح.
run "٢و) text_encoding_locale" python3 -m pytest -q tests_v9/test_text_encoding_locale.py::test_no_new_file_decodes_text_with_the_machines_locale

# ── ٣) أساس الادّعاءات وحارس الطفرات ──────────────────────────────────────
require_file scripts/ci/claim_base_guard.py "٣أ) claim_base_guard" && run "٣أ) claim_base_guard"        python3 scripts/ci/claim_base_guard.py
run "٣ب) guard_mutation (ساكن)"   python3 scripts/ci/guard_mutation_guard.py

# ── ٣ج) نصفُ حارس الطفرات الذي **يزرع** — مقصوراً على ما مسّه تغييرك ────────
# GUARD-MUTATION-PLANTING-HALF-WAS-NEVER-LOCAL-01: خطوة ٣ب أعلاه تفحص **المواصفة**،
# و`preflight_required.json` يعدّ البوّابة مستوفاةً بالاسم — بينما الحاجب في *Unit
# Tests* هو `--run` الذي يزرع العطل فعلاً (`ci.yml:743`). فالعقد يُستوفى والقياس
# غائب، وهو صنف «موجودٌ ≠ يُقاس» بعينه.
#
# والعطل الذي كشفه مقيسٌ لا مُفترَض (96216401333): أضفتُ فحصاً ثانياً إلى
# `knowledge_relation_registry_guard.py` يفشل في الجذر المؤقّت، فصار
# `test_zero_relations_checked_fails_closed` يخضرّ على `SystemExit` **قادمٍ من فحصي**
# لا من البوّابة التي يدّعي حراستها. اختبارٌ يسأل «هل فشل؟» لا «هل فشل لهذا السبب؟».
#
# والزرع الكامل ٢٦٥ طفرة (~٣٨د في CI) لا يسع أيّ طبقة، فيُقصَر على الحرّاس التي
# مسّها التغيير — والمقيس ١١ث لحارسٍ واحد. لا شيء مَسَّه ⇒ لا شيء يُزرَع، بلا ادّعاء.
_mut_targets="$(python3 - "$BASE" <<'MUTPY' 2>/dev/null || true
import json, subprocess, sys

base = sys.argv[1]
registry = json.load(open("docs/architecture/guard_mutation_registry.json", encoding="utf-8"))
spec = registry.get("mutated", {})
# PREFLIGHT-3J-BLIND-TO-BEHAVIOURAL-SOURCES-01: القسمُ السلوكيّ مفاتيحُه مساراتٌ
# كاملة ويحمل طفراتٍ تحجب في CI مثل `mutated` سواء — وكانت الكتلةُ تقرأ `mutated`
# وحدَه، فمصدرٌ سلوكيّ متغيّر يطبع «لا حارسَ مسّه التغيير» زوراً ويمرّ بلا زرع.
behavioural = registry.get("behavioural", {})
# يُصعَّد من ملفّ الاختبار أيضاً: تعديلُ الشاهد وحده يكفي لتقنيع طفرة — وهو ما وقع.
# والاختبارُ الواحد قد يشهد لأكثر من هدفٍ (سلوكيّان يتشاركان ملفّاً) — فمجموعةٌ
# لا مفتاحٌ أخير يُظلِّل ما قبله.
by_test = {}
for section in (spec, behavioural):
    for key, entry in section.items():
        # مفاتيحُ `$…` الوصفيّة قيمُها نصوصٌ لا مداخل — والقسمُ السلوكيّ يحملها فعلاً.
        if not isinstance(entry, dict):
            continue
        # الشاهدُ يُعلَن على المدخل أو على الطفرة المفردة — والصيغتان مشحونتان
        # في السجلّ فعلاً؛ التقاطُ إحداهما وحدها يُعمي التصعيدَ عن الأخرى.
        tests = {entry.get("test")} | {m.get("test") for m in entry.get("mutations", [])}
        for test in tests:
            if test:
                by_test.setdefault(test, set()).add(key)
touched = set()
for cmd in (
    ["git", "diff", "--name-only", f"{base}...HEAD"],
    ["git", "diff", "--name-only", "HEAD"],
    ["git", "ls-files", "--others", "--exclude-standard"],
):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout
    except Exception:
        continue
    for path in out.splitlines():
        if path in by_test:
            touched.update(by_test[path])
        if path in behavioural:
            touched.add(path)
        elif path.rsplit("/", 1)[-1] in spec:
            touched.add(path.rsplit("/", 1)[-1])
print(" ".join(sorted(touched)))
MUTPY
)"
if [ -z "$_mut_targets" ]; then
  echo "── ٣ج) guard_mutation (زرع مقصور)"
  echo "   ✓ لا حارسَ مُواصَفاً مسّه التغيير — لا زرعَ مطلوب"
else
  for _g in $_mut_targets; do
    run "٣ج) guard_mutation --run --only $_g" \
      python3 scripts/ci/guard_mutation_guard.py --run --only "$_g"
  done
fi

# ── ٤) عقود compose/البيئة — أيّ متغيّر جديد يُعلَن في .env.example ─────────
run "٤أ) compose_env_contract"    python3 scripts/ci/compose_env_contract_gate.py
require_file scripts/ci/compose_no_default_secrets_guard.py "٤د) compose_no_default_secrets" \
  && run "٤د) compose_no_default_secrets" python3 scripts/ci/compose_no_default_secrets_guard.py
require_file scripts/ci/compose_auth_sink_guard.py "٤ﻫ) compose_auth_sink" \
  && run "٤ﻫ) compose_auth_sink" python3 scripts/ci/compose_auth_sink_guard.py
require_file scripts/ci/generated_write_targets.py "٤و) generated_write_targets" \
  && run "٤و) generated_write_targets" python3 scripts/ci/generated_write_targets.py --check
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
  # ٦ج تقرأ **رسائل الالتزامات** في `$BASE..HEAD`. فتشغيلُ هذا السكربت قبل الالتزام
  # يقيس مدىً لا يحوي الرسالة التي ستُكتب بعد قليل — وأخضرُه حينئذٍ يقول «ما التُزِم
  # نظيف»، لا «رسالتك ستمرّ». مقيس: التزام يحمل `CI-HOST-PSQL:` في عنوانه — بادئةٌ
  # مبتورة لمعرّف مُسجَّل — مرّ على أخضرِ ٦ج المُشتقّ قبله ثمّ أسقط `guard` في CI.
  # نفس صنف تحذير Capability-Impact أدناه: يُشتقّ بعد الالتزام أو لا يُشتقّ.
  echo "     ملاحظة: ٦ج تقرأ الرسائل **المُلتزَمة**. التزِم ثمّ أعِد هذه الخطوة وحدها."
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
# مداها **٧٤ خطوة على ١٩ workflow** (مقيس على `2bf8814f`)، والمولّدات تبصم مخرجات بعضها: إصلاح واحد
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
  # `env -u PYTHONIOENCODING` صراحةً: `run` يضبطه لأجل طرفيّات Windows، وهذه الخطوة
  # وحدها موجودة **لتقيس متّجه الترميز**، فوراثتُها إيّاه تُبطِل غرضها. النزع هنا هو ما
  # يُبقي الخطوة صادقة. (مقيس: الاختبار يمرّ بلا المتغيّر ويسقط معه.)
  run "١٠) pytest -m unit تحت لغة C" \
    env -u PYTHONIOENCODING LC_ALL=C PYTHONUTF8=0 python3 -m pytest -q -m unit
  # §١٠ أعلاه تُشعِل **الاختبارات** تحت لغة C، ولا تُشعِل الحرّاس أنفسهم — والفرق
  # قِيس ولم يُقدَّر: أوّل إشعالٍ لكلّ حارسٍ في `scripts/ci` أعطى ٣٥ انهياراً في
  # الكتابة و٢٣ في القراءة، وكلّها كانت خضراء لأنّ عدّاء Linux افتراضيّه UTF-8.
  run "١٠ب) كلّ حارسٍ يُشعَل تحت لغة C" python3 scripts/ci/guard_locale_survival_guard.py
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
    echo "   تذكير: البوّابة لا تستمع لـ edited ⇒ تعديل المتن لا يُطلِقها. لكنّها"
    echo "   منذ #907 تقرأ المتن حيّاً من الـAPI زمنَ التنفيذ: rerun يلتقط متناً"
    echo "   محدَّثاً (وSHAs تبقى من الحدث عمداً — البوّابة تحكم على شيفرة الحدث)."
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
  echo "     ولا تدفع متناً بلا السطر. البوّابة لا تستمع لـ edited فالتحرير وحده لا"
  echo "     يُطلِقها — لكنّها منذ #907 تقرأ المتن حيّاً: أضِف السطر ثمّ أعد تشغيلها."
  echo "     اشتقّه بـ: python3 scripts/ci/pr_capability_impact_gate.py --base $BASE --head HEAD"
  skipped=$((skipped + 1))
fi

echo
echo "═══ إخفاقات: $failures · متخطّاة: $skipped ═══"
if [ "$skipped" -gt 0 ]; then
  echo "⚠ $skipped بوّابة لم تُقَس — «لم أنظر» ليس «لا يوجد»."
fi
if [ "$failures" -eq 0 ]; then
  echo "أخضر على ما قِيس. §٣.١٧: workflows تستدعي ٢٦١ بوّابة وهذا يغطّي ٨٦."
  echo "اشتقّ عقود نطاقك من مساراتك المُعدَّلة قبل الدفع."
else
  echo "أصلِح ما فوق. كلّ فشل هنا كان سيكلّف جولة CI كاملة."
fi
[ "$failures" -eq 0 ]
