# قائمة التشغيل الرئيسيّة — بنود «الكود جاهز، ينقص تنفيذ حيّ» (①)

> **الغرض:** الجسر بين «الجرد الصادق» و«التنفيذ الآمن». كلّ بند هنا كوده مدموج ومُختبَر على `main`
> (CI أخضر)، لكنّه يصبح قيمةً فقط حين يمسّه مشغِّل على بيئة التشغيل. هذه القائمة تجيب — قبل أن تُسأل —
> «من أين أبدأ؟ ما ترتيب التبعيّة؟ ما الذي يكسر إن عُكِس الترتيب؟».
>
> **حالة الوثيقة:** مسودّة للمراجعة (spec → review → adopt). لا تُؤرشَف حتّى الاعتماد.
> **الترتيب مقصود:** تصاعُد الخطر — الأصفر أوّلاً (صفر خطر) ← الأحمر آخراً (ترتيب لا يُعكَس).
> **قاعدة ذهبيّة:** كلّ بند له تراجع صريح. لا تبدأ بنداً بلا فهم تراجعه.

| # | البند | الخطر | يعتمد على | رنبوك تفصيليّ |
|---|---|---|---|---|
| ①-1 | دفن الفروع | صفر | — | هذه الوثيقة + `scripts/ops/branch_funeral.py` |
| ①-2 | تفعيل عامل إبطال الكاش | منخفض (عكوس بالراية) | postgres+redis+migrate | هذه الوثيقة |
| ①-3 | **ترقية Decision-Service إلى SoR** | **عالٍ (ترتيب لا يُعكَس)** | **بروفة staging خضراء (مرحلة صفر إلزاميّة)** + migrate + backfill | `DECISION_SERVICE_SOR_*_RUNBOOK.md` ×3 |
| ①-4 | تحقّقات نشريّة + تزويد DEM | منخفض | رفع الخدمات | `REAL_ENV_VERIFICATION_RUNBOOK.md` · `SATELLITE_IMAGERY_RUNBOOK.md` |

---

## ①-1 — دفن الفروع (ابدأ هنا: أسهل، صفر خطر)

- **الشرط المسبق:** صلاحيّة حذف على GitHub (واجهة الويب أو `gh`/توكن بصلاحيّة `repo`). **لا تُحذَف `main` ولا `develop`** (فرعان قانونيّان).
- **الأمر — دفعة أولى (موثَّقة آمنة، محتواها ⊆ main):**
  ```bash
  for b in certification/final-readiness-evidence \
           claude/unify-main-and-certification \
           copilot/29041154936 \
           claude/code-review-34hO3; do
    gh api -X DELETE repos/kafaat/ai_platform_complete_v2.0.0_enhanced/git/refs/heads/$b
  done
  ```
  - **للدفعات اللاحقة (~400 فرعاً مهجوراً):** استعمل الأداة المحروسة — DRY-RUN افتراضيّ، لا تحذف إلّا بـ`--apply`:
    ```bash
    python3 scripts/ops/branch_funeral.py                      # خطّة فقط (DRY-RUN)
    python3 scripts/ops/branch_funeral.py --category merged-pr --apply --limit 30 --yes
    ```
    القاعدة المثبَّتة: **مدموج أو 0-ahead ⇒ حذف فوريّ** · **خامد >30 يوماً ⇒ أرشفة SHA في الدماغ ثمّ حذف على دفعات (~30/أسبوع)**.
- **برهان النجاح:** لكلّ فرع محذوف `git ls-remote --heads origin <b>` **فارغ**، و`gh api repos/.../branches/<b>` → **404**.
- **التراجع:** الفروع المدموجة محتواها ⊆ main ⇒ **لا فقد**. إن لزم، أعِد إنشاء أيّ فرع من SHA المؤرشَف في `sahool-brain`:
  `git push origin <archived-sha>:refs/heads/<b>`.

---

## ①-2 — تفعيل عامل إبطال الكاش (تحقّق نشريّ؛ الكود+compose جاهزان)

> **لماذا ①-2 قبل ①-3 (بحجّتين لا واحدة):**
> - **إحماء يد المشغِّل:** SoR-promotion أثقل إجراء تشغيليّ في السجلّ كلّه (هجرة + backfill + قلب ملكيّة + راية، **بلا تراجع بعد القلب**). تنفيذه كأوّل تماسّ حقيقيّ مع الإنتاج بعد الجلسة = أداء حرِج بيد باردة. ①-2 تماسّ خفيف حقيقيّ يعيد تأهيل الإيقاع — رفع خدمة، قراءة سجلّاتها، إطفاؤها بأمان — قبل عمليّة لا تقبل الارتجال.
> - **فصل أنماط الفشل:** إن كان ثمّة خلل بيئيّ كامن (DNS، secrets، صلاحيّات)، فالأفضل أن يظهر في خدمة مستأجَرة غير حرِجة (عامل إبطال يُطفأ بلا أثر) لا في منتصف قلب ملكيّة SoR. ①-2 هو **اختبار دخان للبيئة مقنَّعاً كعمل منتج**. وقيمة ①-3 العالية لا تتأذّى بتأخير أيّام — محجوبة منذ شهور، والإحماء يرفع نسبة نجاحها لا يخفض قيمتها.

- **الشرط المسبق:** `postgres`+`redis` صحّيان؛ خدمة `sahool-migrate` اكتملت؛ الراية والـDB URL مضبوطان للعامل.
- **الحقيقة (جاهز):** الخدمة **موصولة أصلاً** — `docker-compose.v9.yml:1038` (`sahool-raster-cache-invalidation-worker`)، الراية `RASTER_CACHE_INVALIDATION_ENABLED:-true` (`cache_invalidation_worker.py:67`)، healthcheck heartbeat. الكود مُختبَر (اختبارات تكامليّة خضراء، CI run 28750924733). **الناقص = رفعها فقط.**
- **الأمر:**
  ```bash
  # ضمن الرفع الكامل، أو مفردة:
  docker compose -f docker-compose.v9.yml up -d sahool-raster-cache-invalidation-worker
  # فحص جافّ لدفعة واحدة قبل الحلقة الدائمة (اختياريّ):
  docker compose -f docker-compose.v9.yml run --rm sahool-raster-cache-invalidation-worker \
    python -m cache_invalidation_worker --once
  ```
- **برهان النجاح:** `--once` يطبع `processed N invalidations`؛ healthcheck `worker_heartbeat check --worker raster-cache-invalidation` يمرّ؛ صفّ `pending` في `raster_cache_invalidations` ينتقل إلى `processed` (وتُوسَم `raster_assets.asset_status='stale'` للحقل المعنيّ).
- **التراجع:** `RASTER_CACHE_INVALIDATION_ENABLED=false` + إيقاف الخدمة. الجدول **append-only** ⇒ الطابور يتراكم بلا فقد، والبلاطات تبقى (stale لا خطأ). آمن تماماً.
- **مصاحِب اختياريّ:** إخلاء الكاش (`TILE_CACHE_TTL_SECONDS`/`TILE_CACHE_MAX_BYTES`، `tile_cache_maint.py`) — 0/غياب = مُعطَّل، فعّله بقيَم محافِظة عند الحاجة.

---

## ①-3 — ترقية Decision-Service إلى SoR (الأثقل — الترتيب لا يُعكَس)

> **هذا البند وحده يحمل خطر ترتيب.** القاعدة القاطعة: **schema ثمّ backfill+verify ثمّ قلب الملكيّة** —
> بهذا التسلسل حصراً. القلب قبل امتلاء الجدول = decision-service سلطويّ فارغ **يفقد التاريخ**.
> الرنبوكات الثلاثة الجاهزة تفصّل كلّ مرحلة؛ هذه القائمة تثبّت **الترتيب والحاجز بينها**.

**الشرط المسبق العامّ:** Postgres إنتاجيّ + **دور مقيَّد** لـdecision-service (NOT superuser/BYPASSRLS) + توكن `DECISION_SERVICE_AUTH_TOKEN` مضبوط (وإلّا SoR بلا توكن **يفشل الإقلاع** بالتصميم، `main.py:403`).

### المرحلة صفر — بروفة staging كاملة (إلزاميّة، بوّابة معلَنة لا ضمنيّة)

> **بروفة staging كاملة عبر `DECISION_SERVICE_SOR_STAGING_PROBE_RUNBOOK.md` — لا يُبدأ أيّ إجراء إنتاجيّ في ①-3 قبل إغلاقها ببرهان أخضر، ويُعاد تنفيذها إن تغيّر أيّ migration أو سكربت بين البروفة والتنفيذ.**

- الجملة الأخيرة ليست زينة: **staging تنتهي صلاحيّتها عند أيّ تغيير كود لاحق.** بلا هذا السطر قد تُنفَّذ البروفة ثمّ يمرّ أسبوعان وتُنفَّذ الإنتاجيّة على كود مختلف — وهو نفس درس **«الشهادة تُربَط بالـSHA»** الذي حكم هذه الجلسة كلّها. البروفة برهان مربوط بـSHA؛ تغيّر الـSHA ⇒ بطلت البروفة.
- **برهان إغلاق المرحلة صفر:** بروفة staging خضراء على **نفس SHA** الذي ستُنفَّذ عليه الإنتاجيّة (migrations + `decision_service_migrate.sh` + `backfill.py` بلا تغيير بينهما).

### المرحلة أ — تطبيق المخطّط خارج النطاق (out-of-band، فعل إصدار لا side-effect إقلاع)
```bash
DATABASE_URL='postgresql://<restricted-decision-role>@…/decision' \
DECISION_SERVICE_ALLOW_SCHEMA_CHANGE=true \
bash scripts/deploy/decision_service_migrate.sh
```
- يطبع حالة `--check` قبل وبعد؛ fail-closed بلا `DECISION_SERVICE_ALLOW_SCHEMA_CHANGE=true` (`scripts/deploy/decision_service_migrate.sh:25`).
- **برهان:** post-apply `--check` نظيف (001+002 مطبّقتان، بما فيها طبقة مراجعة WX-10.7).

### المرحلة ب — backfill + verify-review (قراءة فقط؛ الحاجز الحرِج قبل القلب)
```bash
python services/decision-service/backfill.py --verify-review
```
- فحص parity/quarantine للمرشّحين الملتبسين — **يُحلّ كلّ quarantine يدويّاً قبل القلب، لا يُخمَّن** (`backfill.py:17,191`).
- **برهان:** `--verify-review` يعيد **0 quarantine** + parity متطابق مع المنصّة (SoR الحاليّ).
- ⛔ **الحاجز:** لا تنتقل للمرحلة ج قبل أن يكون backfill مكتملاً وverify نظيفاً. **backfill قبل القلب، لا العكس.**

### المرحلة ج — قلب الملكيّة (الفعل السلطويّ الصريح)
```bash
# على خدمة decision-service:
DECISION_SERVICE_SOR_ENABLED=true
DATABASE_URL='postgresql://<restricted-decision-role>@…/decision'   # كلاهما مطلوب معاً
# + قلب ملكيّة loop tables في docs/architecture/db_ownership.yml (decision_record: interim-bridge → decision-service)
```
- الراية وحدها **لا تكفي** لخفض المنصّة — يلزم `DECISION_SERVICE_SOR_ENABLED=true` **و** `DATABASE_URL` معاً (`main.py:475,488`). بلا `DATABASE_URL` مع الراية ⇒ **يرفض المطالبة** ويبقى mirror fail-closed (`main.py:421`).
- **برهان النجاح:** `/readyz` → **200** مع `db_reachable=true` + `migrations_current=true`؛ كتابة قرار جديدة تُخزَّن في decision-service وتُقرأ منه؛ `decision_reviews` سليمة.
- **التراجع (آمن، يصون البيانات):** `DECISION_SERVICE_SOR_ENABLED=false` ⇒ عودة فوريّة لوضع المِرْآة fail-closed (المنصّة تبقى SoR)؛ الراية opt-in افتراض فارغ فالتراجع لا يكسر تنصيباً قائماً؛ rollback **يصون `decision_reviews`**. **لا تُسقِط schema** — البيانات المُدخَلة تبقى للمحاولة التالية.

**الرنبوكات المرجعيّة (تفصيل كلّ مرحلة):** `DECISION_SERVICE_SOR_STAGING_PROBE_RUNBOOK.md` (بروفة staging أوّلاً) → `DECISION_SERVICE_SOR_CUTOVER_RUNBOOK.md` → `DECISION_SERVICE_SOR_PRODUCTION_PROMOTION_RUNBOOK.md`.

---

## ①-4 — تحقّقات نشريّة + تزويد DEM (منخفض الخطر، بعد استقرار ①-3)

| بند فرعيّ | الشرط/الأمر | برهان النجاح | التراجع |
|---|---|---|---|
| **DECISION-DEPLOY** | `docker compose up -d sahool-decision-service` (وضع mirror، `DATABASE_URL` فارغ) | `/healthz`+`/readyz` 200؛ عقد النشر `test_decision_service_deployment_contract.py` أخضر | إيقاف الخدمة؛ المنصّة SoR بالجسر — لا فقد |
| **TERRAIN** | تزويد `FIELD_DEM_PATH` براستر DEM حقيقيّ (`raster_pixel_processing.py:37`) | `GET /v1/fields/{id}/terrain` يعيد `computed=true` بدل مظروف شفّاف | إزالة `FIELD_DEM_PATH` ⇒ عودة صادقة لـ`computed=false` (لا كسر) |
| **CDSE-CLIP / MAPHUB** | تشغيل CDSE حيّ (توكن CDSE) + التحقّق من القصّ على المضلّع | البلاطات مقصوصة على مضلّع الحقل (لا «صحراء حمراء»)؛ `SATELLITE_IMAGERY_RUNBOOK.md` | إيقاف طبقة CDSE؛ الطبقات الأخرى تعمل |

> **صدق:** TERRAIN و SoilGrids **بيانات/بلاطات لا كود** — لا يُختلَق DEM/COG. غيابها يظهر بصدق (شفّاف/`computed=false`/`source_configured=false`)، لا خطأ صامت.

---

## خارج نطاق هذه القائمة (لتفادي الخلط)

- **② محجوب على بيانات حقيقيّة (لن تُختلَق):** SIM-GOLDEN (معايرة PCSE) · معايرة EC ميدانيّة · SoilGrids COG. تُفتَح عند توفّر البيانات، لا بأمر تشغيل.
- **③ مؤجَّل بمحفّز مصمَّم:** ADR-0033 (FIELD-SVC-TENANT-HEADER-TRUST) · WORKER-IDENTITY-BINDING · B3/B4 · موبايل push. تُفتَح بمحفّزها لا بالتشغيل.

---
*المصدر لكلّ سطر: `sahool-brain/gaps/registry.md` · `docker-compose.v9.yml` · `services/raster-service/cache_invalidation_worker.py` · `services/decision-service/{main,backfill,persistence,cutover}.py` · `scripts/deploy/decision_service_migrate.sh` · `scripts/ops/branch_funeral.py`. لا سطر بلا مصدر.*
