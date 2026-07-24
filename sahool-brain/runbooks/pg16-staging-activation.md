# رَنبوك التشغيل — PG16 Staging Activation (فتح البيئة الداخليّة الحيّة)

> **قابل للنسخ من الشاشة.** كتل الأوامر مُصمَّمة للصقّ المباشر في صدفة المُشغّل على بيئة staging.
> **هذا رَنبوك تنسيق (hub) لا تكرار:** يرفع البيئة ويُثبت الأساس، ثمّ **يُحيل** إلى الرَّنبوكات
> التفصيليّة القائمة لكلّ إغلاق. لا يعيد كتابة خطواتها.
>
> **عقد الصدق (صارم):**
> - **الأسرار عبر البيئة فقط.** DSN/كلمات مرور القاعدة (`APP_DB_PASSWORD` · `JOBS_DB_PASSWORD` ·
>   `DATABASE_URL`) تُحقَن من مدير الأسرار/`.env` غير المُتعقَّب — **لا تُكتَب في المحادثة ولا في أيّ ملفّ
>   مُتعقَّب**.
> - **`production_certified` يبقى `false`** حتى تكتمل الشهادة الحيّة وتُوثَّق؛ الكود الساكن لا يمنحها.
> - **`%G? = N`** (غياب توقيع) ليس سبباً لـforce-push على تاريخ main المدموج.
> - لا TLS معطَّل · pip-audit قبل أيّ تغيير تبعيّات.

---

## 0. المتطلّبات المسبقة (Preconditions)

| المطلب | التفصيل | مصدر التحقّق |
|---|---|---|
| صورة PostgreSQL 16 | **تنبيه صدق:** `docker-compose.v9.yml:232,432` تُثبِّت `postgis/postgis:15-3.4` (PG**15**). لـPG16 **تجاوز الصورة** عبر override (أدناه) — لا تُعدَّل القيمة المُتعقَّبة. | `docker-compose.v9.yml:231-232` |
| أدوار القاعدة | `sahool_app` (مقيَّد، RLS مفروض) · `sahool_jobs` (قناة BYPASSRLS الوحيدة، للعمّال) · دور decision-service مقيَّد (ليس superuser). | `scripts/security/rls_runtime_gate.py` |
| أسرار مُحقَنة | `APP_DB_PASSWORD` · `JOBS_DB_PASSWORD` (compose يفشل إن غابا: `:?required`). | `docker-compose.v9.yml:533` |
| الفرع | main مدموج (`64dea36`+) أو الفرع المخصّص. |  |

**تجاوز صورة PG16** (ملفّ override غير مُتعقَّب — لا يمسّ الأصل):
```bash
cat > docker-compose.pg16.override.yml <<'YAML'
services:
  sahool-postgres: { image: postgis/postgis:16-3.4 }
  sahool-migrate:   { image: postgis/postgis:16-3.4 }
YAML
# استخدم -f الأصل + -f التجاوز في كلّ أمر compose أدناه:
export COMPOSE="docker compose -f docker-compose.v9.yml -f docker-compose.pg16.override.yml"
```

---

## 1. رفع PG16 + PostGIS (الطبقة الأساس)

```bash
# الأسرار من مدير الأسرار (مثال محلّيّ فقط؛ في staging تأتي من الأوركستريتور):
export APP_DB_PASSWORD="…"     # لا يُطبع، لا يُلصَق في المحادثة
export JOBS_DB_PASSWORD="…"

$COMPOSE up -d sahool-postgres
# انتظر الجاهزيّة (لا sleep أعمى):
until $COMPOSE exec -T sahool-postgres pg_isready -U postgres >/dev/null 2>&1; do sleep 2; done
echo "postgres ready"

# تأكيد النسخة + PostGIS فعليّاً (برهان لا افتراض):
$COMPOSE exec -T sahool-postgres psql -U postgres -tAc "select version();"
$COMPOSE exec -T sahool-postgres psql -U postgres -tAc "select postgis_full_version();"
```
**بوّابة القرار G1:** إن لم تُظهِر النسخة `PostgreSQL 16` أو فشل PostGIS ⇒ **أوقِف**؛ الصورة/التجاوز خطأ.

---

## 2. تطبيق الهجرات (219) + إثبات RLS

الهجرات تُطبَّق عبر خدمة `sahool-migrate` (خطوة إصدار صريحة، لا أثر جانبيّ لإقلاع) التي تُشغّل
`scripts_v9/run_migrations.sql` (المُولَّد من `migrations/MANIFEST.txt` — المصدر الوحيد، 219 هجرة):

```bash
$COMPOSE up --no-deps --exit-code-from sahool-migrate sahool-migrate
# نجاح = خروج بصفر. فشل أيّ هجرة ⇒ ON_ERROR_STOP يوقف عند أوّل خطأ (لا تطبيق جزئيّ صامت).
```

**إثبات RLS الحيّ بالدور المقيَّد** (لا BYPASSRLS خارج قناة jobs):
```bash
export DATABASE_URL="postgresql://sahool_app:${APP_DB_PASSWORD}@localhost:5432/sahool"
python scripts/security/rls_runtime_gate.py           # يفشل إن كُشِف تسريب دور/BYPASSRLS
python scripts/security/validate_rls_write_policies.py --root .
```

**بوّابة الإنتاج الشاملة** (تشمل RLS + manifest + مصدر الحقيقة + تثبيت الصور):
```bash
bash scripts/production_validation_gate.sh
```
**بوّابة القرار G2:** أيّ فشل هنا ⇒ **أوقِف** وأصلِح قبل أيّ تحويل. هذه أرضيّة الأمان.

---

## 3. مِخطَط decision-service (خطوة خارج النطاق، صريحة)

ترقية مِخطَط decision-service **فعل إصدار مقصود، لا أثر إقلاع**. الغلاف الوحيد المدعوم:

```bash
export DATABASE_URL="postgresql://<decision_role>:<pw>@localhost:5432/sahool"  # دور مقيَّد، ليس superuser
export DECISION_SERVICE_ALLOW_SCHEMA_CHANGE=true                              # فشل-مغلق بدونه
bash scripts/deploy/decision_service_migrate.sh
# يطبع حالة --check قبل/بعد + يشغّل مُتحقِّق مراجعة WX-10.7 (backfill --verify-review):
#   المرشّحات الغامضة تُكشَف قبل قلب الملكيّة، لا تُخمَّن.
```
> **لا** يُفعِّل `DECISION_SERVICE_SOR_ENABLED` ولا يقلب الملكيّة — ذلك فعل مشغّل صريح بعد اخضرار كلّ بوّابة.

---

## 4. سموك الأساس (الخدمات مرفوعة)

```bash
$COMPOSE up -d sahool-platform sahool-nginx    # + الخدمات المطلوبة للبراهين
# صحّة/جاهزيّة حقيقيّة:
curl -fsS localhost:8000/health && echo OK
# اختبارات التكامل (تتطلّب Postgres+PostGIS+Redis مرفوعة — لا تُشغَّل بلا بيئة):
pytest -m integration -q
```

---

## 5. الإغلاقات التي تفتحها هذه البيئة (بترتيب الاعتماديّة)

كلّ بند يُحيل إلى رَنبوكه التفصيليّ القائم — **نفّذه هناك، لا تُكرِّر خطواته:**

### 5.1 تحويل DECISION-SoR (P0 — الأعلى قيمة)
تسلسل البوّابات الحيّة (كلّها بأدوات حقيقيّة موجودة):
1. **مسبار staging** — `services/decision-service/staging_probe.py --tenant-id … --field-id …`
   → [`docs/runbooks/DECISION_SERVICE_SOR_STAGING_PROBE_RUNBOOK.md`](../../docs/runbooks/DECISION_SERVICE_SOR_STAGING_PROBE_RUNBOOK.md)
2. **جاهزيّة التحويل** — `migration_runner.py --check` + `backfill.py --verify-counts` / `--verify-review`
3. **مقارنة جانب القراءة** (dry-run افتراضاً، الوضع الحيّ يتطلّب موافقة صريحة، لا كتابة):
   `services/decision-service/read_side_compare.py`
4. **قرار تحويل بشريّ** ثمّ **الترقية** — `cutover.py` / `production_promotion.py`
   → [`docs/runbooks/DECISION_SERVICE_SOR_CUTOVER_RUNBOOK.md`](../../docs/runbooks/DECISION_SERVICE_SOR_CUTOVER_RUNBOOK.md)
   → [`docs/runbooks/DECISION_SERVICE_SOR_PRODUCTION_PROMOTION_RUNBOOK.md`](../../docs/runbooks/DECISION_SERVICE_SOR_PRODUCTION_PROMOTION_RUNBOOK.md)
5. **قلب الملكيّة ثمّ `REVOKE`** كتابة المنصّة (`DECISION-SOR-CUTOVER-WIRING-01`).
6. **إثبات rollback** — `rollback.py` + health/audit على SHA نفسه (append-only يُحترَم).

### 5.2 SEASON-EDGE-LIVE-PROOF (#225)
مسبار بوّابة nginx الحيّ: X-Canonical مزوَّرة ⇒ 401 · مُراجِع owner/expert ⇒ 200 · إعادة قبول ⇒ 409.
→ [`sahool-brain/runbooks/season-record-entry.md`](season-record-entry.md) §3 (البراهين الحيّة).

### 5.3 إثبات Track 1 الحيّ (MCP فوق CDSE)
الأداة `analyze_field_change` مُغلَقة كوداً (`762dd61`)؛ الإثبات = MCP + raster-service مرفوعان،
نداء حقيقيّ يعيد ملخّص تغيّر من `GET /v1/fields/{id}/timeseries` (fail-closed 424 عند قلّة المشاهدات).

### 5.4 شهادة CDSE/الأقمار الحيّة
→ [`docs/runbooks/SATELLITE_IMAGERY_RUNBOOK.md`](../../docs/runbooks/SATELLITE_IMAGERY_RUNBOOK.md) +
[`docs/runbooks/REAL_ENV_VERIFICATION_RUNBOOK.md`](../../docs/runbooks/REAL_ENV_VERIFICATION_RUNBOOK.md).

---

## 6. الشهادة والصدق (بعد الاخضرار الحيّ فقط)

- `production_certified` يُقلَب إلى `true` **فقط** بعد اكتمال 5.1–5.4 وتوثيق نتائجها في
  [`docs/runbooks/PRODUCTION_CERTIFICATION_CHECKLIST.md`](../../docs/runbooks/PRODUCTION_CERTIFICATION_CHECKLIST.md).
- سجّل النتيجة في الدماغ: `gaps/registry.md` (حالة البنود `fixed`→`verified`) +
  `decisions/ledger.md` (SHA + سبب) + `log.md` (سطر لكلّ إغلاق حيّ).
- **«مؤشّر ≠ إثبات»:** لا تُرقّي بنداً إلى `verified` دون برهان حيّ ملموس (curl/psql/تقرير مسبار).

---

## 7. الإجهاض/التراجع (عند أيّ بوّابة حمراء)

- **قبل قلب الملكيّة:** الإيقاف آمن — لا كتابة أُجريَت (المسبار/المقارنة قراءة-فقط).
- **بعد قلب الملكيّة:** `rollback.py` (append-only، لا حذف) ثمّ إعادة `REVOKE`/`GRANT` للحالة السابقة،
  وتحقّق health/audit على SHA نفسه.
- كلّ خطوة تطبيق تطبع `--check` قبل/بعد ⇒ الحالة مرصودة، لا تخمين.

---

### فهرس الاعتماديّة (مختصر)
```
G1 رفع PG16 ✔ ─▶ G2 هجرات+RLS+validation_gate ✔ ─▶ decision مِخطَط (§3)
                                                   └─▶ 5.1 SoR flip (staging→compare→cutover→promote→revoke→rollback)
                       سموك الأساس (§4) ───────────────▶ 5.2 SEASON-EDGE · 5.3 Track1 MCP · 5.4 CDSE
                                                                              └─▶ §6 شهادة (production_certified=true)
```
