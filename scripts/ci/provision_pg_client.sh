#!/usr/bin/env bash
# عميل PostgreSQL **من صورة الخادم القائمة**، لا من مرآة Ubuntu وقت التشغيل.
#
# CI-PG-CLIENT-VIA-HOST-APT-IS-A-NETWORK-BET-01
# ─────────────────────────────────────────────
# كان `resilient_apt_install.sh postgresql-client` هو الطريق، وسقط مقيساً:
# 2026-08-17 ثلاث مرّات، و2026-08-19 مرّتين في تشغيلٍ واحد (Decision Service
# وLive PG) — في كلّ مرّة ثلاث محاولاتٍ مع تبديل مرآة ثمّ خروجٌ بـ1. والسكربت
# نفسه يقول بنصّه إنّ المهلة «تحوّل الحرق إلى فشل، ولا تُنجح التثبيت»، وإنّ سبب
# المرآة الجذريّ لم يُثبَت. أي أنّه احتواءٌ لعَرَضٍ لا علاج.
#
# والعطل لم يكن ليقف عند وظيفةٍ حمراء: خطوة إنشاء الدور تحتاج `psql`، فغيابه
# جعل `sahool_app` غير موجود، فطبع حارس الإغلاق `RESTRICTED_ROLE_NOT_FOUND` —
# وهي **رسالة عن schema** تُقرأ لاحقاً إثباتاً على عطلٍ في التوفير بينما القاعدة
# لم تبلغ حالةً تُقاس أصلاً. فالعطل البنيويّ كان يتنكّر عطلاً في المجال.
#
# العلاج: الحاوية التي نُشغّلها **تحمل `psql` و`pg_isready` أصلاً** وبنفس إصدار
# الخادم الرئيس. فنُركّب غلافين رفيعين يُمرّران كلّ شيء إلى `docker exec`، بلا
# شبكةٍ خارجيّة وبلا اعتماد على مرآة، وبتطابقٍ في الإصدار كان apt يكسره أحياناً.
#
#   الاستعمال: bash scripts/ci/provision_pg_client.sh <container> <port>
#
# `<port>` هو المنفَذ المنشور على المضيف؛ الغلاف يترجمه إلى 5432 داخل الحاوية
# فتبقى نداءات `-h localhost -p <port>` القائمة صحيحة بلا تعديل موضع استدعاء.
set -euo pipefail

container="${1:?container name required}"
host_port="${2:?published host port required}"
bin_dir="${RUNNER_TEMP:-/tmp}/pg-client-shims"

docker inspect --format '{{.State.Running}}' "$container" >/dev/null 2>&1 || {
  echo "::error::الحاوية '$container' غير قائمة — لا يمكن اشتقاق عميل منها"
  exit 1
}

mkdir -p "$bin_dir"

for tool in psql pg_isready; do
  cat >"$bin_dir/$tool" <<SHIM
#!/usr/bin/env bash
# غلافٌ مولَّد — يُنفّذ $tool داخل '$container' بإصدار الخادم نفسه.
set -euo pipefail
args=()
skip_next=0
for a in "\$@"; do
  if [ "\$skip_next" = 1 ]; then skip_next=0; continue; fi
  case "\$a" in
    # المضيف والمنفَذ يُترجَمان إلى داخل الحاوية: القيمة التالية تُبتلَع معهما.
    -h|--host|-p|--port) skip_next=1; continue;;
    -h*|--host=*|-p*|--port=*) continue;;
    *) args+=("\$a");;
  esac
done
exec docker exec -i \\
  -e PGPASSWORD="\${PGPASSWORD:-}" \\
  "$container" $tool -h 127.0.0.1 -p 5432 "\${args[@]}"
SHIM
  chmod +x "$bin_dir/$tool"
done

# `GITHUB_PATH` يُصدِّر للخطوات التالية؛ و`PATH` هنا يُفيد بقيّة هذه الخطوة.
if [ -n "${GITHUB_PATH:-}" ]; then echo "$bin_dir" >>"$GITHUB_PATH"; fi
export PATH="$bin_dir:$PATH"

echo "عميل PostgreSQL مُشتقٌّ من '$container' (المنفَذ المنشور $host_port) في $bin_dir"
