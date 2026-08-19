#!/usr/bin/env bash
# تثبيتُ حِزَم APT صامدٌ للمرآة — **مسقوفٌ، ومتراجعٌ إلى مرآة أخرى، وقابلٌ للاختبار**.
#
# **العطل، مقيساً في يومٍ واحد ثلاث مرّات على هذا المستودع:**
#   15:53 · `Decision Service Tests` (تشغيل 32156730870)
#   16:14 · `Integration Tests`      (تشغيل 32158772016)
#   18:09 · `Integration Tests`      (تشغيل 32169040894)
# وفي كلٍّ منها: الحاويات أُقلِعت، ثمّ بلغ `apt-get` سقفه الجداريّ (٢٤٠ث) مرّتين،
# فسقطت الوظيفة برسالة مُسمّاة. **والتصلّب عمل**: ثماني دقائق إلى فشلٍ يُقرأ بدل
# ستّ ساعات صامتة. لكنّ تكرارَه ثلاثاً يقول إنّ **الحدّ وحده ليس علاجاً** — يحوّل
# الحرق إلى فشل، ولا يُنجِح التثبيت.
#
# **وما لا يُدّعى:** سببُ تعثّر المرآة غير مُثبَت (ازدحام · DNS · قفل داخليّ). ولذلك
# العلاج **لا يفترض سبباً**: يُعيد المحاولة بتراجعٍ متزايد، ويُبدّل المرآة بين
# المحاولات، ويبقى كلّ استدعاء مسقوفاً. فإن كان العطل عابراً نجحت الثانية، وإن كان
# في مرآةٍ بعينها نجحت الثالثة على غيرها، وإن كان الشبكة كلّها سقط **سريعاً ومُسمّى**.
#
# **ولماذا سكربت لا كتلة داخل YAML** — الدرس المُسجَّل في `resilient_docker_pull.sh`:
# منطقٌ مدفون في `run: |` لا يُقاس إلّا بتشغيل الوظيفة كاملةً، فيبقى «مقيسٌ بمحاكاة»
# ادّعاءً في رسالة التزام. وهنا يُستدعى من `tests_v9/test_resilient_apt_install.py`
# بـ`apt-get` مزيّف فيُقاس كلُّ فرعٍ منه. وثلاثةُ مواضع تُكرّر الكتلة نفسها كانت
# ستنحرف عن بعضها عند أوّل تعديل.
#
# الاستعمال:
#   resilient_apt_install.sh postgresql-client [حزمة أخرى …]
#
# متغيّرات البيئة (لأجل الاختبار، ولضبطٍ موضعيّ عند الحاجة):
#   APT_TIMEOUT   سقف كلّ استدعاء بالثواني (افتراضيّ 240)
#   APT_ATTEMPTS  عدد المحاولات (افتراضيّ 3)
#   APT_BACKOFF   ثواني التراجع الأساسيّة (افتراضيّ 10 ⇒ 10 ثمّ 20 …)
#   APT_FALLBACK_MIRROR  المرآة البديلة (افتراضيّ archive.ubuntu.com)
set -uo pipefail

[ $# -gt 0 ] || { echo "::error::resilient_apt_install: لا حِزَم مطلوبة" >&2; exit 2; }

APT_TIMEOUT="${APT_TIMEOUT:-240}"
APT_ATTEMPTS="${APT_ATTEMPTS:-3}"
APT_BACKOFF="${APT_BACKOFF:-10}"
APT_FALLBACK_MIRROR="${APT_FALLBACK_MIRROR:-archive.ubuntu.com}"

# تبديلُ المرآة مُستخرَجٌ إلى `apt_mirror_fallback.sh` ويشترك فيه هذا السكربت
# و`resilient_playwright_install.sh`: المرآة متّجهٌ واحد يصطدم به الاثنان — مباشرةً
# هنا، ومن جوف الأداة هناك. ونسختان منه تنحرفان عند أوّل تعديل.
# shellcheck source=scripts/ci/apt_mirror_fallback.sh
. "$(dirname "$0")/apt_mirror_fallback.sh"

attempt() {
  sudo timeout -k 10 "$APT_TIMEOUT" apt-get update -qq \
    && sudo timeout -k 10 "$APT_TIMEOUT" apt-get install -y -qq "$@"
}

i=1
while [ "$i" -le "$APT_ATTEMPTS" ]; do
  if attempt "$@"; then
    echo "apt-get نجح في المحاولة $i"
    exit 0
  fi
  echo "apt-get تعثّر/تجمّد (محاولة $i من $APT_ATTEMPTS)"
  if [ "$i" -lt "$APT_ATTEMPTS" ]; then
    # التبديل **قبل** التراجع لا بعده: النوم على مرآةٍ متعثّرة إنفاقُ وقتٍ على
    # نفس الشرط. ويُبدَّل من المحاولة الثانية فصاعداً — الأولى تُجرَّب على
    # الافتراضيّ لأنّه الأسرع حين يعمل.
    switch_apt_mirror
    sleep $((APT_BACKOFF * i))
  fi
  i=$((i + 1))
done

echo "::error::apt-get تجاوز مهلته $APT_ATTEMPTS مرّات (بما فيها مرآة بديلة)" >&2
exit 1
