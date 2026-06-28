#!/usr/bin/env bash
# scripts/deps/lock.sh — توليد/فحص أقفال تبعيّات Python القابلة لإعادة الإنتاج.
# =============================================================================
# الغرض: معالجة انجراف سلسلة الإمداد (build اليوم ≠ build الغد) عبر تثبيت
# نسخ مُحلَّلة بالكامل (transitive) لكلّ ملفّ requirements في المسار الحرج.
#
# لماذا أداة لا أقفال مُلتزَمة سلفاً: يُحلُّ القفل بدقّة CI المستهدَفة (py3.12) عبر
# `--python-version 3.12`، وعبر منصّات متعدّدة بـ`--universal`، فيُنتِج قفلاً واحداً
# مستقرّاً لا يعتمد على مُفسِّر/منصّة المُولِّد — فيتطابق التوليد المحلّيّ مع إعادة الحلّ
# في CI. شغّل التوليد محلّياً ثمّ التزِم النواتج `*.lock`.
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
  # توسعة الأقفال لبقيّة خدمات بوّابة pip-audit الموحّدة (مُتحقَّق نظافتها).
  "services/actuator-service/requirements.txt"
  "services/agriai-engine/requirements.txt"
  "services/edge-inference/requirements.txt"
  "services/indicators-service/requirements.txt"
  "services/mcp_servers/requirements.txt"
  "services/odoo-bridge/requirements.txt"
  "services/qdrant-seed/requirements.txt"
  "services/raster-service/requirements.txt"
  "services/soil-service/requirements.txt"
  "services/supervisor-agent/requirements.txt"
  "services/tts-service/requirements.txt"
  "services/vegetation-analysis-service/requirements.txt"
  "services/video-processor/requirements.txt"
  "services/weather-service/requirements.txt"
  # خدمات خارج بوّابة pip-audit — أقفال لانجراف التبعيّات فقط (لا تدقيق ثغرات حاجب).
  # حُلَّت نظيفة على py3.11/universal ودُقِّقت محليّاً (لا ثغرات معروفة).
  # تُستثنى services/local-ai-rag عمداً: تحمل PYSEC-2026-77 + GHSA-gr75-jv2w-4656
  # (langchain-text-splitters/langchain، إصلاحها خارج سقوف توافق langchain 0.3.x).
  "services/ai_agronomist/requirements.txt"
  "services/field-segmentation/requirements.txt"
  "services/knowledge-graph/requirements.txt"
  "services/rag-retrieval/requirements.txt"
  "services/sam2-inference/requirements.txt"
  "services/weather-polygon-worker/requirements.txt"
  "services/weather-signal-engine/requirements.txt"
)

# دقّة الحلّ المستهدَفة = الأدنى المدعوم (python 3.11، مطابِق لصور python:3.11-slim).
# ‏--universal يجعل الناتج صالحاً لـ3.11 و3.12 معاً، فيبقى --require-hashes داخل
# صور 3.11 متوافقاً، ويبقى فحص CI (setup-python 3.12) أخضر لأنّ uv يحلّ لـ3.11
# من هذا المتغيّر لا من مُفسِّر المُولِّد. غيّرها هنا فقط.
PY_TARGET="3.11"

# أعلام موحَّدة للتوليد والفحص كي يتطابق الناتجان بايتاً ببايت:
# --generate-hashes: تثبيت تجزئة لكلّ توزيعة (سلسلة إمداد قابلة للتدقيق).
# --universal + --python-version: حلٌّ مستقلّ عن منصّة/مُفسِّر المُولِّد ومطابق لـCI.
# --custom-compile-command: ترويسة ثابتة لا تُسرِّب مسار -o (وإلّا أبلغ --check انجرافاً زائفاً).
UV_FLAGS=(
  --quiet
  --generate-hashes
  --universal
  --python-version "$PY_TARGET"
  --custom-compile-command "scripts/deps/lock.sh"
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
    uv pip compile "${UV_FLAGS[@]}" "$req" -o "$tmp"
    if [ ! -f "$lock" ] || ! diff -q "$lock" "$tmp" >/dev/null 2>&1; then
      echo "انجراف قفل: $lock لا يطابق إعادة حلّ $req — شغّل scripts/deps/lock.sh" >&2
      rc=1
    else
      echo "OK: $lock محدَّث"
    fi
    rm -f "$tmp"
  else
    echo "قفل: $req -> $lock"
    uv pip compile "${UV_FLAGS[@]}" "$req" -o "$lock"
  fi
done

exit "$rc"
