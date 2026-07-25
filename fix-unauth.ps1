# اضبط المتغيّرات (PowerShell)
$env:EXPECTED_SHA       = "0da934a"
$env:DATABASE_URL       = "postgresql://sahool_app:PASSWORD@HOST:5432/sahool"   # دور NOBYPASSRLS
$env:SAHOOL_AGENT_TOKEN = "التوكن_الحقيقيّ"
$env:FIELD_SERVICE_URL  = "http://127.0.0.1:8099"                              # خدمة field-management الجارية
$env:TENANT_A           = "uuid-المستأجر-A"
$env:TENANT_B           = "uuid-المستأجر-B"
$env:FIELD_A            = "field_id-مملوك-لـA"

# شغّل البوّابة عبر bash (Git Bash/WSL موجود على PATH)
bash scripts/staging/field_management_live_gate.sh

إن لم يتوفّر bash في PowerShell، افتح Git Bash مباشرةً في نفس المجلّد وشغّل بصيغة bash:
Now

