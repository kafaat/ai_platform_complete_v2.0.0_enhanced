#!/usr/bin/env bash
# سحبُ صورة بمحاولات متدرّجة — **يفشل مغلقاً**، وقابلٌ للتنفيذ فيُختبَر.
#
# العطل الذي وُجِد لأجله، مقيساً: الصياغة الأولى كانت `docker pull X && break` داخل
# حلقة. و`docker pull` ليس آخِر أمرٍ في قائمة `&&`، فلا يُسقِطه `set -e`؛ فتُستنفَد
# المحاولات ويُكمِل التنفيذ إلى `docker run` برسالةٍ أغمض. لاحظه Copilot.
#
# **ولماذا سكربت لا كتلة داخل YAML:** المنطق المدفون في `run: |` لا يُختبَر إلّا
# بتشغيل الوظيفة كاملةً في CI، فيبقى «مقيسٌ بمحاكاة» ادّعاءً في رسالة التزام.
# هنا يُستدعى من `tests_v9/test_resilient_docker_pull.sh.py` بـ`docker` مزيّف،
# ويُثبَت أنّ الاستدعاء التالي **لم يُنفَّذ**.
#
# الاستعمال: resilient_docker_pull.sh <image> [attempts]
set -euo pipefail

image="${1:?اسم الصورة مطلوب}"
attempts="${2:-6}"

for i in $(seq 1 "$attempts"); do
  if docker pull "$image"; then
    exit 0
  fi
  # لا نوم بعد المحاولة الأخيرة: ٦٠ ثانية تُنفَق ثمّ يُعلَن الفشل على أيّ حال.
  if [ "$i" -lt "$attempts" ]; then
    echo "pull $image فشل (محاولة $i من $attempts) — backoff" >&2
    sleep $((i * 10))
  fi
done

echo "::error::تعذّر سحب $image بعد $attempts محاولات" >&2
exit 1
