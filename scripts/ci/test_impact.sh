#!/usr/bin/env bash
# ============================================================================
# test_impact.sh — يُشغّل الاختبارات التي يمسّها تغييرك، لا الجناح كلّه
# ============================================================================
#   bash scripts/ci/test_impact.sh              # يشتقّ الخطّة ثمّ يُشغّلها (-m unit)
#   bash scripts/ci/test_impact.sh --plan       # يطبع الخطّة ولا يُشغّل شيئاً
#   bash scripts/ci/test_impact.sh --marker ""  # بلا علامة (كلّ ما يُجمَع)
#   BASE=origin/develop bash scripts/ci/test_impact.sh
#
# ── صفتها: تسريع محلّيّ، ليست بوّابة ولا بديلاً عن CI ──────────────────────
# أخضرها يعني «ما اختير مرّ». والاختيار محدود بما يعرفه محرّك أثر القدرات:
# **٤٨٪ من حالات جناح الوحدة تقع في ملفّات لا يبلغها أيّ مخروط** (مقيس 2026-08-05)
# فتعمل دائماً كأرضيّة. أقصى ما توفّره الأداة تنصيفُ الجناح لا إلغاؤه.
#
# ولا تملك منطق أثر خاصّاً بها: كلّ قدرة تأتي من `pr_capability_impact_gate`
# نفسه الذي تستدعيه البوّابة الحاجبة — لأنّ محرّكين للسؤال الواحد قاسا في هذا
# المستودع ٠ و١٢ على مُدخل واحد (CAPABILITY-IMPACT-TOOLS-DISAGREE-01).
# ============================================================================
set -uo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "✗ لست داخل شجرة عمل git — الاشتقاق يحتاج تاريخاً" >&2; exit 2
}
cd "$ROOT" || exit 2

PLAN_ONLY=0
MARKER="unit"
while [ $# -gt 0 ]; do
  case "$1" in
    --plan) PLAN_ONLY=1 ;;
    --marker) shift; [ $# -gt 0 ] || { echo "✗ --marker يحتاج قيمة" >&2; exit 2; }; MARKER="$1" ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "✗ راية غير معروفة: $1" >&2; exit 2 ;;
  esac
  shift
done

BASE="${BASE:-origin/main}"

python scripts/ci/test_impact.py --base "$BASE" || exit 2
[ "$PLAN_ONLY" -eq 1 ] && exit 0

mapfile -t PATHS < <(python scripts/ci/test_impact.py --base "$BASE" --print-paths) || exit 2
if [ "${#PATHS[@]}" -eq 0 ]; then
  echo "✗ الخطّة لم تُنتِج مساراً واحداً — لا يُفترَض نجاح على لا شيء" >&2
  exit 2
fi

echo
echo "── تشغيل ${#PATHS[@]} ملفّاً${MARKER:+ بعلامة $MARKER} ──"
if [ -n "$MARKER" ]; then
  python -m pytest -q -m "$MARKER" "${PATHS[@]}"
else
  python -m pytest -q "${PATHS[@]}"
fi
rc=$?

echo
echo "أخضر هنا يعني «ما اختير مرّ». القرار النهائيّ لـCI."
exit $rc
