#!/usr/bin/env bash
# generate_mbtiles.sh — يولّد حزمة MBTiles لمنطقة (للعمل offline على الموبايل).
#
# سدّ فجوة بيئة اليمن ضعيفة الشبكة: يحزّم بلاطات الخلفيّة لمنطقة (الجوف/
# السنيدار) في ملفّ MBTiles واحد يُشحَن للجهاز أو يُنزَّل عند أوّل اتّصال.
#
# يحتاج (على جهازك): gdal (gdal_translate, gdaladdo) أو mb-util.
# الاستخدام:
#   ./generate_mbtiles.sh aljawf 44.0 16.5 45.0 17.2 8 15
#   (الوسائط: الاسم west south east north zoom_min zoom_max)
#
# المخرج: <name>.mbtiles في مجلّد offline_packs بخدمة الراستر.

set -euo pipefail

NAME="${1:-region}"
WEST="${2:?حدّد west}"
SOUTH="${3:?حدّد south}"
EAST="${4:?حدّد east}"
NORTH="${5:?حدّد north}"
ZMIN="${6:-8}"
ZMAX="${7:-15}"

OUT_DIR="${OFFLINE_PACKS_DIR:-./offline_packs}"
mkdir -p "$OUT_DIR"
OUT="$OUT_DIR/${NAME}.mbtiles"

echo "═══ توليد حزمة MBTiles: $NAME ═══"
echo "  النطاق: [$WEST,$SOUTH,$EAST,$NORTH] zoom $ZMIN-$ZMAX"

# تحقّق من توفّر الأدوات
if ! command -v gdal_translate >/dev/null 2>&1; then
  echo "✗ gdal غير متوفّر. ثبّته: apt-get install gdal-bin"
  echo "  أو استخدم mb-util / tilemill لتوليد MBTiles."
  exit 1
fi

# ملاحظة: التوليد الفعلي يتطلّب مصدر بلاطات (XYZ أو COG). هذا قالب — صِل
# مصدرك (ArcGIS World Imagery أو COG محلّي) ثمّ شغّل التحويل.
echo "  ⚠ صِل مصدر البلاطات (XYZ template أو COG) قبل التشغيل الفعلي."
echo "  مثال (من COG محلّي):"
echo "    gdal_translate -of MBTILES input.tif $OUT"
echo "    gdaladdo -r average $OUT 2 4 8 16    # أهرامات للتكبير"
echo ""
echo "  بعد التوليد، انقل $OUT إلى offline_packs بخدمة الراستر،"
echo "  ثمّ يظهر في GET /offline/packs ليحمّله الموبايل."

# صدق: لا نزيّف توليداً يحتاج مصدراً + gdal. نوفّر القالب والتوجيه الصحيح.
