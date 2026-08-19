#!/usr/bin/env bash
# المُشغّل **القانونيّ الوحيد** لبيان الهجرات — تعريفٌ واحد لعبارة «طُبِّق البيان».
#
# MIGRATION-STDIN-OWNERSHIP-01
# ────────────────────────────
# كانت الحلقة تُعدّد البيان من **مجرى حيّ**:
#
#     while read -r f; do psql … -f "migrations/$f"; done < <(grep … MANIFEST.txt)
#
# فمَن يملك `fd 0` أثناء التنفيذ هو نفسه مَن يحمل بقيّة القائمة. و`psql` الأصليّ
# مع `-f` لا يمسّه، لكنّ غلاف العميل المُحوَّى يُشغّل `docker run -i` فيُمرّر
# المجرى إلى حاويةٍ عابرة تستنزفه. المقيس في 32285597465:
#
#     init_v8.sql → PASS   ·   هجرات مُطبَّقة: 1 من 226   ·   ثمّ EOF
#
# ولم يكن ذلك عطلاً في `init_v8.sql` ولا في PostgreSQL/PostGIS ولا في أيّ هجرةٍ
# لاحقة — بل **تصادمُ ملكيّةٍ على مجرى الدخل**. وتَبِعه في Integration انفجارٌ
# ثانويّ: 57 فشلاً و23 خطأً كلّها `relation … does not exist`، وليست تشخيصاً.
#
# ── دفاعان، وكلاهما مطلوب ────────────────────────────────────────────────────
# ① `mapfile`: البيان يُقرأ **لقطةً ثابتة قبل** أوّل تنفيذ، فلا يبقى مجرىً حيّاً
#    يملكه أحد أثناء العمل.
# ② `</dev/null` لكلّ استدعاء: حتّى لو عاد عميلٌ يستنزف الدخل مستقبلاً، فلا مجرى
#    تحكّمٍ لديه ليسرقه. الأوّل يُصلح اليوم، والثاني يمنع عودة الصنف كلّه.
#
# ويُفحَص وجودُ كلّ ملفٍّ **قبل لمس القاعدة**، فلا تُترَك قاعدةٌ نصفَ مُهاجَرة عند
# اسمٍ خاطئ في البيان. وسِجلّه يقول أين وصل بالضبط (`migration[k/N]`) بدل «1 من
# 226» التي لا تدلّ على آخر ما دخل.
#
#   الاستعمال: apply_migration_manifest.sh --port 5435 --user sahool_user --db sahool
set -euo pipefail

port=""; user=""; database=""; host="localhost"
manifest="migrations/MANIFEST.txt"; stop_before=""; root="."
while [ "$#" -gt 0 ]; do
  case "$1" in
    --host) host="$2"; shift 2;;
    --port) port="$2"; shift 2;;
    --user) user="$2"; shift 2;;
    --db|--database) database="$2"; shift 2;;
    --manifest) manifest="$2"; shift 2;;
    # تطبيقٌ محدود: يقف **قبل** أوّل ملفٍّ يطابق النمط. تحتاجه بوّابة الترقية U1
    # التي تُثبِت حالةَ ما قبل v195 ثمّ تُرقّي — وكانت تحمل نسختها الخاصّة من
    # الحلقة المعطوبة (`applied 1 migrations (pre-v195)` في 32290853228).
    --stop-before) stop_before="$2"; shift 2;;
    --root) root="$2"; shift 2;;
    *) echo "::error::وسيطٌ غير معروف: $1"; exit 2;;
  esac
done
: "${port:?--port required}" "${user:?--user required}" "${database:?--db required}"

mig_dir="migrations"
if [ "$root" != "." ]; then mig_dir="${root%/}/migrations"; fi

[ -f "$manifest" ] || { echo "::error::MIGRATION_MANIFEST_MISSING: $manifest"; exit 1; }

# ① لقطةٌ ثابتة قبل التنفيذ — لا مجرى حيّ يملكه أحد.
mapfile -t migrations < <(grep -vE '^[[:space:]]*(#|$)' "$manifest")
expected="${#migrations[@]}"
[ "$expected" -gt 0 ] || { echo "::error::MIGRATION_MANIFEST_EMPTY: $manifest"; exit 1; }

# فحصُ الوجود **قبل** لمس القاعدة: اسمٌ خاطئ لا يترك قاعدةً نصفَ مُهاجَرة.
# الحدّ يُطبَّق على اللقطة قبل الفحص، فيُفحَص ما سيُطبَّق فعلاً لا أكثر.
if [ -n "$stop_before" ]; then
  bounded=()
  for f in "${migrations[@]}"; do
    case "$f" in $stop_before) break;; esac
    bounded+=("$f")
  done
  migrations=("${bounded[@]+"${bounded[@]}"}")
  expected="${#migrations[@]}"
  [ "$expected" -gt 0 ] || { echo "::error::MIGRATION_BOUND_EXCLUDED_EVERYTHING: $stop_before"; exit 1; }
fi

missing=()
for f in "${migrations[@]}"; do
  [ -f "$mig_dir/$f" ] || missing+=("$f")
done
if [ "${#missing[@]}" -gt 0 ]; then
  echo "::error::MIGRATION_FILE_MISSING: ${missing[*]}"
  exit 1
fi

applied=0
for f in "${migrations[@]}"; do
  # ② مجرى دخلٍ معزول لكلّ استدعاء — لا يستطيع ابنٌ سرقة تحكّم الأب.
  psql -X -h "$host" -p "$port" -U "$user" -d "$database" \
    -v ON_ERROR_STOP=1 -q -f "$mig_dir/$f" </dev/null
  applied=$((applied + 1))
  printf 'migration[%d/%d] %s\n' "$applied" "$expected" "$f"
done

if [ "$applied" -ne "$expected" ]; then
  echo "::error::MIGRATION_APPLY_COUNT_MISMATCH: applied=$applied expected=$expected"
  exit 1
fi
echo "migration_manifest_applied ok applied=$applied expected=$expected"
