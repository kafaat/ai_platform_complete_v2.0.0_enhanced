# RIV Durable Product Identity and Recoverable Batch Leases

Date: 2026-07-12

## Scope

This increment closes database-level raster product uniqueness and durable,
restart-recoverable batch claims for Raster–Indicators–Vegetation processing.

## Implemented

### Full raster product identity

Added migration `migrations/v147_raster_product_identity_batch_leases.sql`.
A raster product is now identified by a deterministic `product_identity_key`
derived from:

- tenant
- field geometry hash/revision
- scene
- indicator
- algorithm version
- QA mask version

The underspecified v145 unique index is removed and replaced by the partial
unique index `uq_raster_assets_product_identity`.

The raster writer now persists:

- `product_identity_key`
- `algorithm_version`
- `qa_mask_version`
- `field_geometry_hash`

and performs `ON CONFLICT (product_identity_key) DO UPDATE`.

### Durable batch jobs and leases

Added the tenant-isolated `raster_batch_jobs` table with:

- one authoritative row per deterministic claim key
- processing status
- lease owner and opaque lease token
- lease expiry
- request/result payloads
- attempt count
- terminal outcome

`POST /process/batch` now prefers a PostgreSQL atomic claim. Redis/memory is
used only when the database is unavailable. Expired processing leases can be
recovered after a worker crash; completed and failed jobs converge on the same
canonical job ID.

### Stale-worker protection

Heartbeat and terminal writes require both the current worker and the opaque
lease token. An old process cannot finish a lease that has been recovered by a
new worker, even when both use the same worker name.

Lease tokens are stored in a process-private map and are never included in the
public `/jobs/{id}` payload.

### Runtime configuration

Added and aligned in both Compose variants and `.env.example`:

- `RASTER_BATCH_CLAIM_TTL_SECONDS=86400`
- `RASTER_BATCH_LEASE_SECONDS=300`
- `RASTER_WORKER_ID=raster-api`

The fixed Compose Raster service now also receives PostgreSQL and Redis and
waits for migrations/database/cache readiness.

## Verification

Focused suite:

```text
31 passed
```

CI guards:

```text
riv_boundary_gate_ok
raster_production_truth_guard_ok
geospatial_contract_index_ok
indicators_registry_gate_ok
```

Python compilation and Compose YAML parsing passed.

## Honest remaining runtime certification

This environment did not provide a live PostgreSQL/Redis/MinIO/Docker stack.
The following must still be demonstrated in staging:

1. Apply v147 on a real Postgres instance under the migration role.
2. Start two Raster workers and submit the same batch concurrently.
3. Verify one database lease winner and one canonical job ID.
4. Kill the winner, wait for lease expiry, and verify recovery by worker two.
5. Verify the stale worker cannot heartbeat or write terminal state.
6. Reprocess the same scene with a changed algorithm/mask/geometry and verify a
   separate product row is created.
7. Process the exact same full identity and verify no duplicate asset row.
8. Exercise remote COG reads from MinIO/S3 and collect throughput/memory/cache
   metrics.

---

## ملحق التكامل (أُضيف عند الدمج على الشجرة المُهبَطة — 2026-07-12)

قاعدة الحزمة `3b20e07` (متأخّرة). قرارات الدمج:

- **تصادم ترقيم الهجرة (مصحَّح):** الحزمة رقّمت الهجرة `v147`، لكنّ الشجرة المُهبَطة
  تستخدم v145/v146/v147 لأغراض أخرى ورأسها v153. أُعيد ترقيمها إلى
  **`v154_raster_product_identity_batch_leases.sql`** وأُضيفت إلى `migrations/MANIFEST.txt`
  وإلى `scripts_v9/run_migrations.sql` (خطوة 160)، وحُدِّث مرجع الاختبار الساكن. أُكِّد
  فهرس v145 المُستبدَل (`uq_raster_assets_product`) هو الموجود فعلاً على الشجرة.
- **برهان على Postgres حقيقيّ:** طُبِّقت v154 داخل معاملة (rolled back) على PG محلّيّ —
  جدول `raster_batch_jobs` أُنشئ، فهرس `uq_raster_assets_product_identity` استبدل الأضيق،
  وRLS+FORCE مفعَّلان (`t|t`). اختبار الهويّة الدائمة 6/6، مجموعة raster 239.
- **النطاق المأخوذ (الزيادة الصحيحة، مفصولة الاعتماديّة):** هجرة v154 + جدول المطالبة
  الدائمة (`raster_batch_job_store`) + إيجارات العامل (`raster_batch_runtime_leases`) +
  هويّة المنتج في الكاتب (`db_persist` ON CONFLICT على `product_identity_key`،
  `raster_asset_persistence` يحسب الهويّة) + مسار `/process/batch` يفضّل مطالبة PG
  الذرّيّة مع ارتداد Redis/memory + heartbeat/finish للإيجار في التنسيق + رايات
  compose(v9+fixed)/‏env (`RASTER_BATCH_LEASE_SECONDS`, `RASTER_WORKER_ID`).
- **مؤجَّل صراحةً (زيادة منفصلة عالية الأثر):** التقرير الثاني في الحزمة
  (RIV_REGISTRY_CONTRACT_BUNDLE) — إعادة تسمية تصنيف السجلّ (`real→observed/unavailable`،
  مخطّط v1→v2) + `geospatial_intelligence_contracts.json` + حارسه + نقطة
  `indicator-observation-bundle`. **سبب التأجيل:** حارسه يشترط مخطّط v2 ويمنع البدائل
  الدلاليّة (`savi→msavi`, `ndmi→moisture`) الحاملة في كودنا المُهبَط، ومولِّده يعيد
  إدخال انحدار manifest الواجهة الذي أصلحته سابقاً — هذه هجرة تصنيف كاملة تستحقّ
  تمريرةً خاصّة، لا دلتا آمنة فوق الهويّة الدائمة.
- **تحقّق محلّيّ:** raster 239 · بطاريّة ما-قبل-الدمج (بما فيها بوّابات Structural Lint
  التي أُضيفت للبطاريّة بعد درس CI) خضراء · manifest الإصدار (4124) + الجرد مُجدَّدان.
