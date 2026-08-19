#!/usr/bin/env bash
# عميل PostgreSQL **من الصورة المسحوبة أصلاً**، لا من مرآة Ubuntu وقت التشغيل.
#
# CI-PG-CLIENT-VIA-HOST-APT-IS-A-NETWORK-BET-01
# ─────────────────────────────────────────────
# كان `resilient_apt_install.sh postgresql-client` هو الطريق، وسقط مقيساً: ثلاث
# مرّات في ٢٠٢٦-٠٨-١٧ (موثَّقة داخل ذلك السكربت)، ومرّتين في تشغيلٍ واحد
# ٢٠٢٦-٠٨-١٩ (Decision Service وLive PG) — في كلٍّ ثلاث محاولاتٍ مع تبديل مرآة
# ثمّ خروجٌ بـ1. والسكربت نفسه يقول إنّ المهلة «تحوّل الحرق إلى فشل، ولا تُنجح
# التثبيت». أي أنّه احتواءُ عَرَضٍ لا علاج.
#
# ولم يقف الأثر عند وظيفةٍ حمراء: خطوة إنشاء الدور تحتاج `psql`، فغيابه جعل
# `sahool_app` غير موجود، فطبع حارس الإغلاق `RESTRICTED_ROLE_NOT_FOUND` — رسالةً
# **عن schema** عن قاعدةٍ لم تبلغ حالةً تُقاس. فتنكّر عطلٌ بنيويّ عطلاً في المجال.
#
# ── لماذا `docker run` على الصورة، لا `docker exec` في الحاوية ────────────────
# أوّل صيغةٍ كتبتُها نفّذت `psql` **داخل** حاوية الخادم، فسقطت مقيسةً بـ
# `psql: error: migrations/init_v8.sql: No such file or directory`: الرايةُ `-f`
# يحلّها **العميل** من نظام ملفّاته، وشجرةُ المستودع لا وجود لها داخل الحاوية.
# فالصيغة الصحيحة حاويةٌ عابرة من **الصورة نفسها** (فلا سحبَ إضافيّ ولا شبكة):
#   · `--network host` ⇒ `-h localhost -p <port>` تعمل كما هي، فلا تُعاد كتابة
#     أيّ وسيط — وإعادةُ الكتابة كانت مصدر العطل الثاني المحتمل.
#   · `-v "$PWD:$PWD" -w "$PWD"` ⇒ `-f migrations/…` و`\copy` تحلّ مساراتها.
#   · إصدار العميل = إصدار الخادم، وهو ما كان apt يكسره أحياناً.
#
#   الاستعمال (والتصدير **لازم** في الخطوة نفسها):
#     bash scripts/ci/provision_pg_client.sh <container>
#     export PATH="${RUNNER_TEMP:-/tmp}/pg-client-shims:$PATH"
#
# `GITHUB_PATH` يخدم الخطوات التالية وحدها؛ و`export` داخل هذا السكربت يموت مع
# عمليّته — وهو العطل الذي أسقط `Integration Tests` في أوّل تشغيل. فالتصدير في
# الخطوة صريحٌ، ويحرسه `test_provision_pg_client.py` كي لا يعود سقوطه صامتاً.
set -euo pipefail

container="${1:?container name required}"
bin_dir="${RUNNER_TEMP:-/tmp}/pg-client-shims"

image="$(docker inspect --format '{{.Config.Image}}' "$container" 2>/dev/null || true)"
if [ -z "$image" ]; then
  echo "::error::الحاوية '$container' غير قائمة — لا صورة تُشتقّ منها أدوات العميل"
  exit 1
fi

mkdir -p "$bin_dir"

for tool in psql pg_isready; do
  cat >"$bin_dir/$tool" <<SHIM
#!/usr/bin/env bash
# غلافٌ مولَّد — $tool من '$image' بشبكة المضيف وشجرة العمل مركَّبة كما هي.
set -euo pipefail
exec docker run --rm -i --network host \\
  -v "\$PWD:\$PWD" -w "\$PWD" \\
  -e PGPASSWORD="\${PGPASSWORD:-}" \\
  -e PGHOST -e PGPORT -e PGUSER -e PGDATABASE \\
  "$image" $tool "\$@"
SHIM
  chmod +x "$bin_dir/$tool"
done

if [ -n "${GITHUB_PATH:-}" ]; then echo "$bin_dir" >>"$GITHUB_PATH"; fi

echo "عميل PostgreSQL من صورة '$image' في $bin_dir (صدِّر PATH في هذه الخطوة)"
