#!/usr/bin/env bash
# scripts/deps/lock.sh — توليد/فحص أقفال تبعيّات Python القابلة لإعادة الإنتاج.
# =============================================================================
# الغرض: معالجة انجراف سلسلة الإمداد (build اليوم ≠ build الغد) عبر تثبيت
# نسخ مُحلَّلة بالكامل (transitive) لكلّ ملفّ requirements في المسار الحرج.
#
# لماذا أداة لا أقفال مُلتزَمة سلفاً: يجب أن يُحلَّل القفل في بيئة الهدف ذاتها
# (إصدار Python ومنصّة CI = ubuntu-24.04/py3.12)، وإلّا اختلفت النسخ. شغّل هذا
# داخل CI أو حاوية مطابقة، ثمّ التزِم النواتج `*.lock`.
#
# الاستخدام:
#   scripts/deps/lock.sh            # يولّد <req>.lock بجانب كلّ ملفّ هدف
#   scripts/deps/lock.sh --check    # يفشل (CI) إن انجرف أيّ قفل عن مصدره
#
# المتطلّب: uv (https://docs.astral.sh/uv/). لا شبكة؟ سيفشل uv بوضوح.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

# المسار الحرج الذي تحجبه بوّابة Security Scan (pip-audit) في CI — انظر CLAUDE.md.
TARGETS=(
  "services/sahool-platform/api/requirements.txt"
  "services/auth/requirements.txt"
  "services/guardrails-engine/requirements.txt"
  "requirements_real.txt"
)

if ! command -v uv >/dev/null 2>&1; then
  echo "خطأ: uv غير مثبَّت. ثبّته: https://docs.astral.sh/uv/" >&2
  exit 2
fi

CHECK=0
[ "${1:-}" = "--check" ] && CHECK=1

rc=0
for req in "${TARGETS[@]}"; do
  [ -f "$req" ] || { echo "تخطٍّ (غير موجود): $req"; continue; }
  lock="${req%.txt}.lock"
  if [ "$CHECK" -eq 1 ]; then
    tmp="$(mktemp)"
    uv pip compile --quiet --generate-hashes "$req" -o "$tmp"
    if [ ! -f "$lock" ] || ! diff -q "$lock" "$tmp" >/dev/null 2>&1; then
      echo "انجراف قفل: $lock لا يطابق إعادة حلّ $req — شغّل scripts/deps/lock.sh" >&2
      rc=1
    else
      echo "OK: $lock محدَّث"
    fi
    rm -f "$tmp"
  else
    echo "قفل: $req -> $lock"
    uv pip compile --quiet --generate-hashes "$req" -o "$lock"
  fi
done

exit "$rc"
