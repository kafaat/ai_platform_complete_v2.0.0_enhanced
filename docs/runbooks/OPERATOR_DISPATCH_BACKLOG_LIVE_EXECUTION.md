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
| **①-0** | **حاجبا مفتاح الإيقاف — مرفوعان** (`fixed` بتفويض مقيَّد؛ GATE-01 نفسها باقية CLOSED) | مرفوع — تحقَّق فقط (القسم أدناه) | — (أُنجز تحت `GATE01-ADJ-2026-08-13-001`) | `sahool-brain/gaps/registry.md` + القسم أدناه |
| ①-1 | دفن الفروع | صفر | — | هذه الوثيقة + `scripts/ops/branch_funeral.py` |
| ①-2 | تفعيل عامل إبطال الكاش | منخفض (عكوس بالراية) | postgres+redis+migrate | هذه الوثيقة |
| ①-3 | **ترقية Decision-Service إلى SoR** | **عالٍ (ترتيب لا يُعكَس)** | **بروفة staging خضراء (مرحلة صفر إلزاميّة)** + migrate + backfill | `DECISION_SERVICE_SOR_*_RUNBOOK.md` ×3 |
| ①-4 | تحقّقات نشريّة + تزويد DEM | منخفض | رفع الخدمات | `REAL_ENV_VERIFICATION_RUNBOOK.md` · `SATELLITE_IMAGERY_RUNBOOK.md` |

---

## ①-0 — حاجبا مفتاح الإيقاف: **مرفوعان** (تصحيح 2026-08-23 — كان هذا القسم يصفهما مفتوحين)

> **الحاجبان أُغلقا.** كلاهما `fixed` في [`sahool-brain/gaps/registry.md`](../../sahool-brain/gaps/registry.md)
> (رُفع الحجر بقرار المالك 2026-08-12)، والرقعتان هبطتا تحت **تفويض مقيَّد** —
> [`GATE01-ADJ-2026-08-13-001`](../architecture/gates/adjudications/GATE01-ADJ-2026-08-13-001.json)
> (مربوط بالبايتات، PR #837، مختوم `CONSUMED` بدمج `09dbaeb7`) — **دون فتح GATE-01**، التي
> تبقى `CLOSED` عالميّاً. هذه الوثيقة وصفتهما `OPEN` حتى 2026-08-23 بينما السجلّ يقول
> `fixed` — والقاعدة التي خرقها هذا النثر هي نفسها المكتوبة فيه: السجلّ مصدر الحقيقة،
> لا أيّ نثر تشغيليّ.

| المعرّف | الموضع | العلّة (تاريخيّة) والحال |
|---|---|---|
| `COMPENSATION-BYPASSES-KILLSWITCH-01` | `services/actuator-service/actuator_runtime.py` (`_compensate`) | **كانت** حلقة التعويض تُرسِل الأمر العكسيّ بلا استشارة `is_actuation_halted`. **أُصلِح**: الاستشارة تقع الآن عبر `_consult_killswitch` (بما فيها الاستشارة المنطاقة داخل الحلقة). الحالة في السجلّ: `fixed`. |
| `MANUAL-COMMAND-KILLSWITCH-SCOPE-BLIND-01` | `services/actuator-service/routers/commands.py` | **كان** `/v1/command` اليدويّ يفحص المفتاح بلا `field_id`. **أُصلِح**: يمرَّر `field_id=device_field_id, valve_id=req.device_id` من المُصرِّح نفسه. الحالة في السجلّ: `fixed`. |

**حالة الأدلّة والاختبارات (المقيسة، لا المفترَضة):**
- حزمة أدلّة المرحلة 0 **مجمَّدة** في [`gate01_policy.json`](../architecture/gate01_policy.json) v2
  (المحكَّم 2026-08-13): `phase0_baseline.commit_sha=6ba0bef56f47926ce657515fe1717019522f868b` ·
  تشغيل `31701614219` بنتيجة `success` · ثلاث بصمات مصنوعات مرسَّاة. الصياغة القديمة هنا
  (`frozen_commit_sha=null` · `NOT_FROZEN`) سبقت التحكيم ولم تُحدَّث. (مرساة المرحلة 0 هي
  `6ba0bef5…` — لا تُخلَط بمرساة runbook القبول الحيّ `19747b82…`؛ السياسة v2 فصلت
  الدلالتين عمداً.)
- علامتا `xfail(strict=True)` **نُزِعتا** من
  [`tests_v9/test_compensation_killswitch.py`](../../tests_v9/test_compensation_killswitch.py)
  و[`tests_v9/test_manual_command_killswitch_scope.py`](../../tests_v9/test_manual_command_killswitch_scope.py)
  عند هبوط الرقعتين — والاختباران الآن واصفان للسلوك **القائم**: آخر قياس 2026-08-23 على
  `main@19747b82`: **17/17 passed** في ~2.1s.

### اسأل عن الإذن قبل أن تسأل عن التنفيذ

**العطل وقع مرّتين (2026-08-09 و2026-08-13)، وفي المرّتين نُفِّذت رقعةٌ كاملة ثمّ أُرجِعت
بايتاً.** والسبب واحد في المرّتين: قِيس «كيف أُصلِح» قبل «أمسموحٌ أن أُصلِح»، والجواب كان
في الشجرة طوال الوقت. وليست المسألة انضباطاً شخصيّاً — السجلّ يقول: **«التعديل يزيد
الإيقاف» ليس استثناءً؛ كلّ من يُعدّل مساراً يظنّ تعديله تحسيناً.**

فقبل لمس أيّ ملفٍّ في هذا المسار، شغّل هذا — يُجيب بنعم أو لا، ولا يحتاج قراءةَ نثر:

```bash
git diff --name-only origin/main...HEAD \
  | python3 scripts/ci/gate01_frozen_path_guard.py --stdin
```

`exit 0` ⇒ لم تمسّ مجمَّداً. و`exit 1` ⇒ مسست، والرسالة تسمّي الملفّ ومعرّف الفجوة
والسبيل. ولمعرفة ما هو مجمَّد أصلاً قبل أن تبدأ:

```bash
python3 -c "import json;d=json.load(open('docs/architecture/gate01_policy.json'));\
print(d['gate']['state']);print(*d['frozen_paths'],sep='\n')"
```

**وحدُّ الحارس مكتوبٌ فيه:** يمنع مسّاً غير مأذون فقط — لا يفتح البوّابة، ولا يُثبِّت
أدلّة، ولا يحكم على صحّة التعديل. وخضرتُه تعني «لم يُمَسّ مسارٌ مجمَّد» لا «التغيير سليم».
وفتحُ البوّابة يبقى بقرار مالكٍ صريح على SHA نهائيّ.

**انحدارٌ جديد محروس:** [`scripts/ci/actuation_killswitch_coverage_guard.py`](../../scripts/ci/actuation_killswitch_coverage_guard.py)
يرصد **موضع الاستدعاء** (لا النصّ) فيُسقِط CI على أيّ موضع إطلاق **جديد** بلا مفتاح.
و`FROZEN_EXCEPTIONS` فيه **فارغ اليوم**: قيد `_compensate` نُزِع فور هبوط رقعته كما
يقتضي الإنفاذ العكسيّ — فمن ينزع الاستشارة غداً يسقط أحمر، لا يمرّ بترخيصٍ ميّت.

**ما يفعله المشغِّل هنا:** لا شيء تنفيذيّاً — الحاجبان مرفوعان، والتحقّق صار توثيقيّاً:
الرقعتان في الشجرة والاختبارات خضراء (أعلاه). **وGATE-01 نفسها باقية `CLOSED`** ولم يكن
فتحُها شرطاً لهذا القسم (التفويض المقيَّد كفى) — ما يزال خلفها مؤجَّلاً: كاتب
`online_learning_updates` (يظهر `gate01_deferred=1` في حارس writer-cutover) وشريحة
التحكّم التنفيذيّ المحجوبة (`migrations/v228…` وأخواتها في `not_yet_in_tree`). فتحُها
انتقالُ مرحلةٍ بقرار مالكٍ صريح، ويلزم قبل أيّ عملٍ يمسّ المسارات المجمَّدة في ①-3.

---

## ①-1 — دفن الفروع (ابدأ هنا: أسهل، صفر خطر)

- **الشرط المسبق:** صلاحيّة حذف على GitHub (واجهة الويب أو `gh`/توكن بصلاحيّة `repo`). **لا تُحذَف `main` ولا `develop`** (فرعان قانونيّان).
- **⚠ تحقّق ما قبل الحذف — خاصّ بـ`claude/code-review-34hO3` (لا يُتخطّى):** هو الفرع الوحيد في الدفعة الذي كان **متقدّماً 22 commit** على main في آخر فحص، وادّعاء حصاده (Windows-encoding) جاء تقريراً لا بسطر إثبات. قبل حذفه تحديداً:
  ```bash
  git fetch && git log --oneline main..origin/claude/code-review-34hO3
  ```
  - **فارغ** أو كلّ ما فيه مدموج معروف ⇒ احذف بأمان.
  - **أيّ commit غير محصود** ⇒ **توقّف**، التقطه بنفس مسار الانتقاء الجراحيّ (cherry-pick)، ثمّ احذف. (رخيص، ويمنع رمي عملٍ آخر بالخطأ في فرعٍ أثبت أنّه ينبت commits باستمرار.)
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

**الشرط المسبق العامّ:** [**①-0 مرفوع**](#①-0--حاجبا-مفتاح-الإيقاف-مرفوعان-تصحيح-2026-08-23--كان-هذا-القسم-يصفهما-مفتوحين) (**متحقّق منذ 2026-08-13**: الفجوتان `fixed`، والقسم أعلاه صار توثيقيّاً — لكن انتبه: أيّ عملٍ في ①-3 يمسّ مساراً مجمَّداً ما يزال خلف GATE-01 الـ`CLOSED`) + Postgres إنتاجيّ + **دور مقيَّد** لـdecision-service (NOT superuser/BYPASSRLS) + توكن `DECISION_SERVICE_AUTH_TOKEN` مضبوط (وإلّا SoR بلا توكن **يفشل الإقلاع** بالتصميم، `main.py:403`).

> **وقبل أيّ `REVOKE`:** شهادة الأدوار `DECISION-SOR-PRE-CUTOVER-ROLE-CERTIFICATION` (قراءة فقط، بلا خطر) عبر `services/decision-service/decision_sor_role_certify.py` — دوران مشتركان ⇒ **لا REVOKE**. يفصّلها [`DECISION_SOR_CUTOVER.md`](DECISION_SOR_CUTOVER.md).

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
- **توضيح (قلب الملكيّة تغيير مستودع لا خطوة خادميّة):** تعديل ملكيّة loop tables في `db_ownership.yml` يُنفَّذ كـ**PR عاديّ (مراجعة + CI أخضر + إعادة توليد)** قبل ضبط الراية — لأنّ الحُرّاس الساكنة تقرأه، والانجراف بين الملفّ والواقع يُحمِّر البوّابات. الراية خطوة خادميّة؛ الملكيّة خطوة مستودع — لا تخلطهما.
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
