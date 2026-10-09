#!/usr/bin/env bash
# سحبُ صورة بمحاولات متدرّجة — **يفشل مغلقاً**، وقابلٌ للتنفيذ فيُختبَر.
#
# العطل الذي وُجِد لأجله، مقيساً: الصياغة الأولى كانت `docker pull X && break` داخل
# حلقة. و`docker pull` ليس آخِر أمرٍ في قائمة `&&`، فلا يُسقِطه `set -e`؛ فتُستنفَد
# المحاولات ويُكمِل التنفيذ إلى `docker run` برسالةٍ أغمض. لاحظه Copilot.
#
# **ولماذا سكربت لا كتلة داخل YAML:** المنطق المدفون في `run: |` لا يُختبَر إلّا
# بتشغيل الوظيفة كاملةً في CI، فيبقى «مقيسٌ بمحاكاة» ادّعاءً في رسالة التزام.
# هنا يُستدعى من `tests_v9/test_resilient_docker_pull.py` بـ`docker` مزيّف،
# ويُثبَت أنّ الاستدعاء التالي **لم يُنفَّذ**.
#
# الاستعمال: resilient_docker_pull.sh <image> [attempts]
set -euo pipefail

image="${1:?اسم الصورة مطلوب}"
attempts="${2:-6}"
if ! [[ "$attempts" =~ ^[1-9][0-9]*$ ]]; then
  echo "::error::عدد محاولات السحب غير صالح" >&2
  exit 2
fi

# **سقفٌ لكلّ محاولة.** الحلقة تحدّ **عدد** المحاولات ولا تحدّ **مدّة** الواحدة،
# فمحاولةٌ عالقة تبتلع الوظيفة كلّها ولا تصل الحلقة إلى التالية — وهو الصنف الذي
# علّق `Integration Tests` في تشغيل 32073296568. سقفُ الوظيفة (`#868`) يقتلها بعد
# ثلاثين دقيقة؛ وهذا يجعلها **تُعاد** بدل أن تُقتَل.
PULL_TIMEOUT="${PULL_TIMEOUT:-300}"
output="$(mktemp)"
trap 'rm -f "$output"' EXIT

registry="${image%%/*}"
if [[ "$image" != */* || "$registry" != *.* && "$registry" != *:* && "$registry" != localhost ]]; then
  registry=docker.io
fi

for i in $(seq 1 "$attempts"); do
  if timeout "$PULL_TIMEOUT" docker pull "$image" >"$output" 2>&1; then
    cat "$output"
    exit 0
  else
    pull_status=$?
  fi
  cat "$output" >&2
  output_lower="$(tr '[:upper:]' '[:lower:]' <"$output")"
  if [[ "$output_lower" == *toomanyrequests* || "$output_lower" == *"429 too many"* || "$output_lower" == *"pull rate limit"* ]]; then
    failure_class=RATE_LIMIT
  elif grep -Eqi 'HTTP[^0-9]{0,8}5[0-9][0-9]|5[0-9][0-9][[:space:]]+(internal server error|service unavailable|bad gateway|gateway timeout)' "$output"; then
    failure_class=REGISTRY_5XX
  elif [[ "$pull_status" -eq 124 || "$output_lower" == *"context deadline exceeded"* || "$output_lower" == *"client.timeout"* || "$output_lower" == *"i/o timeout"* || "$output_lower" == *"operation timed out"* ]]; then
    if [[ "$output_lower" == *auth.docker.io* ]]; then
      failure_class=AUTH_TIMEOUT
    else
      failure_class=NETWORK_TIMEOUT
    fi
  elif [[ "$output_lower" == *unauthorized* || "$output_lower" == *"authentication required"* || "$output_lower" == *"denied"* ]]; then
    failure_class=AUTH_FAILURE
  else
    failure_class=REGISTRY_ERROR
  fi

  if [[ -n "${HARNESS_PRIMARY_CAUSE_FILE:-}" ]]; then
    printf '%s\n' DOCKER_IMAGE_PULL_FAILED >"$HARNESS_PRIMARY_CAUSE_FILE"
    echo "::error::root_cause=DOCKER_IMAGE_PULL_FAILED image=$image registry=$registry failure_class=$failure_class database_state=NOT_STARTED evidence_state=HARNESS_INVALID" >&2
  else
    echo "::error::root_cause=DOCKER_IMAGE_PULL_FAILED image=$image registry=$registry failure_class=$failure_class" >&2
  fi

  if [[ "$failure_class" == RATE_LIMIT ]]; then
    echo "::error::توقّف السحب فوراً بعد حدّ 429؛ إعادة المحاولة لن تزيل الحدّ" >&2
    break
  fi
  # لا نوم بعد المحاولة الأخيرة: ٦٠ ثانية تُنفَق ثمّ يُعلَن الفشل على أيّ حال.
  if [ "$i" -lt "$attempts" ]; then
    echo "pull $image فشل (محاولة $i من $attempts، $failure_class) — backoff" >&2
    sleep $((i * 10))
  fi
done

echo "::error::تعذّر سحب $image بعد ${i:-0}/$attempts محاولات" >&2
exit 1
