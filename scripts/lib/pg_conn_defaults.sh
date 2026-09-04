# scripts/lib/pg_conn_defaults.sh — **التعريف الواحد** لوجهة PostgreSQL.
#
# يُصدَّر منه: PGHOST · PGPORT · PGUSER · PGDATABASE. وتبقى `PGPASSWORD` خارج
# المستودع دائماً (تُمرَّر عبر البيئة، ولا سرّ افتراضيّ هنا).
#
# ## لماذا ملفٌّ ثالث بدل قيمتين متطابقتين
#
# كان لكلٍّ من `backup_postgres.sh` و`restore_postgres.sh` جدولُ افتراضاتٍ خاصّ به،
# فانحرفا: النسخُ الاحتياطيّ يقصد `sahool-postgres`/`sahool_user` — وهو ما في
# `docker-compose.v9.yml` فعلاً — والاستعادةُ تقصد `sahool-postgis`/`postgres`،
# وهو مضيفٌ **لا وجود له** في الملفّ القانونيّ (الاسمُ يعيش في
# `docker-compose.light.yml` وحدَه، وبدورٍ ثالثٍ هو `sahool_app`).
#
# وأخطرُ ما فيه أنّ `restore_postgres.sh` كان يقول في تعليقه **«نفس قيم
# backup_postgres.sh»** — أي انحرافٌ يحمل معه **دعوى عدم الانحراف**. فمن يقرأ
# التعليق لا يفحص، ومن لا يفحص يكتشف الفرقَ في اللحظة الوحيدة التي لا تحتمل
# اكتشافاً: لحظةَ الاستعادة بعد فقدِ البيانات.
#
# و`test_backup_script_targets_real_service_and_role` كان يفرض الزوجَ الصحيحَ
# **على النسخ الاحتياطيّ وحدَه**، ويسمّي `sahool-postgis/postgres` خطأً بالحرف —
# أي حارسٌ يصف العطلَ بدقّة ولا ينظر إلى الملفّ الذي يحمله. حارسُ نصفِ الزوج.
#
# فالعلاجُ ليس مطابقةَ القيمتين — تلك تنحرف غداً كما انحرفت أمس — بل **إلغاء
# الثانية**: مصدرٌ واحدٌ يقرأ منه الطرفان، وتغييرُ الوجهة يقع في موضعٍ واحد.

: "${PGHOST:=sahool-postgres}"
: "${PGPORT:=5432}"
: "${PGUSER:=sahool_user}"
: "${PGDATABASE:=sahool}"

export PGHOST PGPORT PGUSER PGDATABASE
