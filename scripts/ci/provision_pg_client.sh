#!/usr/bin/env bash
# عميل PostgreSQL **من الصورة المسحوبة أصلاً**، لا من مرآة Ubuntu وقت التشغيل.
#
# CI-PG-CLIENT-VIA-HOST-APT-IS-A-NETWORK-BET-01
# ─────────────────────────────────────────────
# كان `resilient_apt_install.sh postgresql-client` هو الطريق، وسقط مقيساً: ثلاث
# مرّات في ٢٠٢٦-٠٨-١٧ (موثَّقة داخل ذلك السكربت)، ومرّتين في تشغيلٍ واحد
# ٢٠٢٦-٠٨-١٩. والسكربت نفسه يقول إنّ المهلة «تحوّل الحرق إلى فشل، ولا تُنجح
# التثبيت» — احتواءُ عَرَضٍ لا علاج.
#
# ولم يقف الأثر عند وظيفةٍ حمراء: خطوة إنشاء الدور تحتاج `psql`، فغيابه جعل
# `sahool_app` غير موجود، فطبع حارس الإغلاق `RESTRICTED_ROLE_NOT_FOUND` — رسالةً
# **عن schema** عن قاعدةٍ لم تبلغ حالةً تُقاس. فتنكّر عطلٌ بنيويّ عطلاً في المجال.
#
# ── ثلاثة عيوبٍ في هذا الغلاف نفسه، كلٌّ مقيسٌ بتشغيل ────────────────────────
# ① `docker exec` داخل حاوية الخادم ⇒ `psql: error: migrations/init_v8.sql: No
#    such file or directory` (32280469751). الرايةُ `-f` يحلّها **العميل** من
#    نظام ملفّاته، وشجرةُ المستودع لا وجود لها داخل الحاوية. فصار حاويةً عابرة من
#    **الصورة نفسها** بـ`--network host` وتركيبِ شجرة العمل — فلا سحبَ إضافيّ، ولا
#    حاجة إلى إعادة كتابة `-h/-p` إطلاقاً.
# ② `export PATH` هنا يموت مع عمليّة هذا السكربت، و`GITHUB_PATH` يخدم الخطوات
#    **التالية** وحدها. فبقيت الأداة مفقودة وسقطت `Integration Tests`. فالتصدير
#    لازمٌ في الخطوة نفسها، ويحرسه `test_provision_pg_client.py`.
# ③ `docker run -i` **يستنزف stdin** (32283081538). وخطوة الهجرات حلقةٌ تقرأ
#    قائمتها من مجرى دخلها، فالتهم أوّلُ استدعاءٍ بقيّةَ القائمة وانتهت الحلقة
#    **خضراء بلا جداول** ثمّ سقطت 57 حالة بـ`relation ... does not exist`.
#    فصار `-i` يُوصَل عند الحاجة فقط: مع `-f` لا وصل، وبدونها يبقى للمستندات.
#
#   الاستعمال (والتصدير **لازم** في الخطوة نفسها):
#     bash scripts/ci/provision_pg_client.sh <container>
#     export PATH="${RUNNER_TEMP:-/tmp}/pg-client-shims:$PATH"
set -euo pipefail

container="${1:?container name required}"
bin_dir="${RUNNER_TEMP:-/tmp}/pg-client-shims"

image="$(docker inspect --format '{{.Config.Image}}' "$container" 2>/dev/null || true)"
if [ -z "$image" ]; then
  echo "::error::الحاوية '$container' غير قائمة — لا صورة تُشتقّ منها أدوات العميل"
  exit 1
fi

mkdir -p "$bin_dir"

# المستند **مقتبس** فلا يُوسَّع شيءٌ وقت التوليد — وهو العيب الذي جعل جسد الغلاف
# يُنفَّذ في المُولِّد بدل أن يُكتَب. والنائبان يُستبدلان بعده بـ`sed`.
for tool in psql pg_isready; do
  cat >"$bin_dir/$tool" <<'SHIM'
#!/usr/bin/env bash
# غلافٌ مولَّد — @@TOOL@@ من '@@IMAGE@@' بشبكة المضيف وشجرة العمل مركَّبة كما هي.
set -euo pipefail
attach=()
needs_stdin=1
for a in "$@"; do
  case "$a" in
    -f | --file | -f* | --file=*) needs_stdin=0 ;;
  esac
done
if [ "$needs_stdin" = 1 ]; then attach=(-i); fi
exec docker run --rm ${attach[@]+"${attach[@]}"} --network host \
  -v "$PWD:$PWD" -w "$PWD" \
  -e PGPASSWORD="${PGPASSWORD:-}" \
  -e PGHOST -e PGPORT -e PGUSER -e PGDATABASE \
  '@@IMAGE@@' @@TOOL@@ "$@"
SHIM
  sed -i "s|@@IMAGE@@|${image}|g; s|@@TOOL@@|${tool}|g" "$bin_dir/$tool"
  chmod +x "$bin_dir/$tool"
done

if [ -n "${GITHUB_PATH:-}" ]; then echo "$bin_dir" >>"$GITHUB_PATH"; fi

echo "عميل PostgreSQL من صورة '$image' في $bin_dir (صدِّر PATH في هذه الخطوة)"
