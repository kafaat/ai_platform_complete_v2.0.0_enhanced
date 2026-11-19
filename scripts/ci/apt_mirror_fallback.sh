# shellcheck shell=bash
# تبديلُ مرآة APT — دالّةٌ واحدة يشترك فيها كلّ من يصطدم بالمرآة نفسها.
#
# **لماذا مُستخرَجة لا منسوخة.** المرآة هي المتّجه المقيس المشترك: `apt-get` يستدعيها
# مباشرةً، و`playwright install --with-deps` يستدعيها **من جوفه**. ونسختان من هذا
# المنطق تنحرفان عند أوّل تعديل — وهو الدرس المُسجَّل في `resilient_docker_pull.sh`
# ثمّ في كتل APT الثلاث التي وُحِّدت لأجله.
#
# **وحدُّها مُعلَن:** تبديل المرآة **تحسينُ فرصة لا شرطُ صحّة**. فغيابُ ملفّ المصادر
# — أو تعذّر تحريره — لا يُفشِل المُستدعي: إفشالُ تثبيتٍ لأنّ ملفّ إعدادٍ ليس حيث
# توقّعناه يُحوّل علاجاً إلى عطلٍ جديد. تُعيد صفراً دائماً، وتطبع ما فعلت.
#
# تُصدَّر عبر `source`، ولا تُنفَّذ وحدها.

APT_FALLBACK_MIRROR="${APT_FALLBACK_MIRROR:-archive.ubuntu.com}"

# مصادر APT على ubuntu-24.04 بصيغة deb822 في `ubuntu.sources`؛ والأقدم في
# `sources.list`. والمساران **يُحقَنان** لا يُصلَّبان:
#
# أوّل صياغة كتبتهما حرفيّاً داخل الدالّة، فصار اختبارُ «تُبدَّل المرآة قبل النوم»
# يمرّ أو يسقط **بحسب نظام ملفّات المُشغِّل**: يزيّف `sed` لكنّه لا يُستدعى أصلاً إن
# لم يوجد أيّ من الملفّين. أمسكها مراجعٌ خارجيّ على مُشغِّلٍ بلا `/etc/apt`، ومرّت
# هنا لأنّ الملفّين موجودان — أي أنّ الاختبار كان **يقيس البيئة لا السكربت**، وهو
# الصنف الذي يُسمّى أخضرَ ثمّ يحمرّ عند غيره بلا تغييرٍ في الشيفرة.
#
# **و`apt-mirrors.txt` أوّلاً — مقيسٌ من سجلّ CI (2026-09-30، تثبيت Playwright على
# `b0c14b6d`):** مُشغِّلاتُ GitHub تقرأ مرآتها من `mirror+file:/etc/apt/apt-mirrors.txt`
# (سطر `Get:1 file:/etc/apt/apt-mirrors.txt Mirrorlist`)، فلا يحمل `ubuntu.sources`
# اسمَ المضيف أصلاً. طُبِع «المرآة بُدِّلت» ثمّ جلب التحديثُ التالي من
# `azure.archive.ubuntu.com` نفسِه: التبديلُ لم يقع، والرسالةُ ادّعته.
APT_SOURCE_FILES="${APT_SOURCE_FILES:-/etc/apt/apt-mirrors.txt /etc/apt/sources.list.d/ubuntu.sources /etc/apt/sources.list}"
_APT_HOST_RE='[a-z0-9.-]*\.archive\.ubuntu\.com'

switch_apt_mirror() {
  local f switched=""
  # shellcheck disable=SC2086 — قائمةُ مسارات مفصولة بفراغ عمداً، لا كلمةٌ واحدة.
  for f in $APT_SOURCE_FILES; do
    [ -f "$f" ] || continue
    # `sed -i` يُعيد صفراً ولو لم يستبدل شيئاً — فرمزُه يقيس «الملفُّ قابلٌ للتحرير» لا
    # «بُدِّلت المرآة». الادّعاءُ مشروطٌ بوجود المضيف قبل التحرير.
    grep -q "$_APT_HOST_RE" "$f" || continue
    if sudo sed -i "s|$_APT_HOST_RE|$APT_FALLBACK_MIRROR|g" "$f"; then
      switched="$switched $f"
    fi
  done
  if [ -n "$switched" ]; then
    echo "المرآة بُدِّلت إلى $APT_FALLBACK_MIRROR في:$switched"
  else
    echo "لم تُبدَّل المرآة: لا مضيف *.archive.ubuntu.com في ($APT_SOURCE_FILES)"
  fi
  return 0
}

# انتظارُ apt يتيمٍ يحمل قفل dpkg قبل المحاولة التالية.
#
# **مقيسٌ من السجلّ نفسِه:** `timeout` أنهى المحاولةَ الأولى من `playwright install
# --with-deps`، لكنّ `apt-get` الذي يستدعيه عبر `sudo` **بقي حيّاً** يُكمل التنزيل
# (Get:16–20 بعد إعلان المهلة) ويحمل `/var/lib/dpkg/lock-frontend`. فسقطت المحاولتان
# الثانية والثالثة في ~٣ث لكلٍّ على القفل — لم تكونا إعادةَ محاولة، بل الفشلَ الأوّل
# مُكرَّراً. واليتيمُ كان على وشك الإتمام.
#
# لا يُقتَل: قتلُ `dpkg` أثناء التثبيت يُفسد حالته. يُنتظَر حتّى السقف، ويُسمّى إن بقي.
wait_for_apt_idle() {
  local cap="${1:-300}" poll="${APT_IDLE_POLL:-5}" waited=0 busy
  while busy="$(pgrep -a -x 'apt-get|apt|dpkg' 2>/dev/null)" && [ -n "$busy" ]; do
    if [ "$waited" -ge "$cap" ]; then
      echo "apt ما زال يحمل القفل بعد ${cap}ث — المحاولةُ التالية قد تسقط عليه: $busy"
      return 0
    fi
    [ "$waited" = 0 ] && echo "انتظارُ apt يتيمٍ من المحاولة السابقة يحمل القفل: $busy"
    sleep "$poll"
    waited=$((waited + (poll > 0 ? poll : 1)))
  done
  [ "$waited" -gt 0 ] && echo "تحرّر قفلُ apt بعد ${waited}ث"
  return 0
}
