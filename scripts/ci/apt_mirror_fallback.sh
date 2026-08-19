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
# `sources.list`. يُبدَّل ما وُجِد منهما.
switch_apt_mirror() {
  local f changed=0
  for f in /etc/apt/sources.list.d/ubuntu.sources /etc/apt/sources.list; do
    [ -f "$f" ] || continue
    if sudo sed -i "s|[a-z0-9.-]*\.archive\.ubuntu\.com|$APT_FALLBACK_MIRROR|g" "$f"; then
      changed=1
    fi
  done
  [ "$changed" = 1 ] && echo "المرآة بُدِّلت إلى $APT_FALLBACK_MIRROR"
  return 0
}
