# 🗄️ فهرس الترحيلات (Migrations) بالمجال

> فهرس مُجمَّع بالمجال للمصدر القانونيّ [`../../migrations/MANIFEST.txt`](../../migrations/MANIFEST.txt)
> (97 ترحيلاً، تُطبَّق بالترتيب الصريح لا الأبجديّ). الترتيب الأبجديّ يضع v10 قبل v9 ⇒ كسر
> الاعتماديّات؛ لذا MANIFEST يفرض التسلسل (`MANIFEST.txt:1-19`).

## الأساس (Foundation)

`init_v8.sql` (extensions: postgis/uuid-ossp/pgcrypto + core) → `v9_foundation.sql` (جداول v9
المرجعيّة بـFK) → `v10_command_store_lifecycle.sql` → `v11_events_bus.sql` →
`v12_trueup_sharing.sql` → `v13_geospatial_core.sql`. (`MANIFEST.txt:21-43`)

## المصادقة والمستخدمون (Auth)

`v9_auth_improvements.sql`, `v21_mfa.sql` (TOTP)، `v40_verification.sql` (تأكيد بريد/هاتف)،
`v89_invitations.sql`، **`v97_user_self_with_check.sql`** (يُصلح فشل `/v1/auth/register` بـ
`InsufficientPrivilegeError` — `WITH CHECK` صريح يسمح بالتسجيل التأسيسيّ دون كسر العزل،
`MANIFEST.txt:397-400`؛ يُكمِّل auth-fix #437).

## الحقول والمواسم والعمليّات (Fields / Seasons / Activities)

`v19_farms.sql` (هرميّة مزرعة→حقل)، `v30_fields_geometry.sql`، `v32_seasons.sql`،
`v35_activities.sql`، `v44_one_active_season.sql` (موسم نشط واحد لكلّ حقل)،
`v52_season_agronomy_fields.sql`، `v61/v64_*row_version` (تزامن تفاؤليّ 409)،
`v62_field_lifecycle_null_season_guard.sql`. (`MANIFEST.txt:62-228`)

## نمذجة الأحداث (Eventing / Outbox / Replay)

`v11_events_bus.sql`، `v18_entity_ids_text.sql`، `v46_lifecycle_event_sync.sql`،
**`v63_events_seq_deterministic_order.sql`** (عمود `seq` يكسر تعادل `occurred_at` ⇒ حتميّة
الإعادة)، `v72_event_outbox_rls.sql`، `v93_processed_events.sql` (استهلاك idempotent، at-most-once).

## النظم المكانيّة (GIS / PostGIS)

`v13_geospatial_core.sql`، `v27_gis_enforce.sql` (trigger يرفض geom غير صالحة)،
`v43_fields_geom_index.sql` (GiST)، `v58/v59_*boundary*` (جودة الحدود + طوبولوجيا حتميّة)،
**`v96_spatial_geometry_integrity.sql`** (`field_geometry_history` سجلّ مراجعات +
`raster_cache_invalidations` طابور إبطال كاش، `MANIFEST.txt:392-396`).

## سلسلة القرار والنَّسَب (Decision v78–v79 + ما حولها)

- **`v77_recommendations.sql`** — تخزين + تدقيق التوصية (يُصدِر `RECOMMENDATION_CREATED`، يسدّ C1/C2).
- **`v78_decision_record.sql`** — إدامة رأس القرار (`decision_id`/نوعه/قيمته JSONB/ثقته) كرأس سلسلة
  Decision→Outcome→Evidence (`MANIFEST.txt:293-296`). يخدمه [`decision_record.py`](../../services/sahool-platform/api/routers/decision_record.py).
- **`v79_outcome_record.sql`** — إدامة نتيجة القرار مربوطةً بـ`decision_id` (يُغلق حلقة
  Decision→Outcome، P0-1، `MANIFEST.txt:298-301`).
- `v66/v67/v68_*dispatch/execution_ledger`، `v82_lineage_link.sql` (معرّف `lin_` موحّد).

## الحافة والأمان (Edge + Security، v92–v97)

`v9_edge_idempotency.sql`/`v9_edge_occurred_at.sql`، `v81_actuator_command_dedup.sql`
(dedup cluster-safe)، `v90_break_glass.sql` (وصول مدير عابر مُدقَّق)،
**`v92_offline_pending_ops.sql`** (طابور offline دائم)، `v93_processed_events.sql`،
**`v94_scouting_pins.sql`** (دبابيس الاستطلاع الدائمة — كانت session-only)،
**`v95_prescriptions.sql`** (وصفات المعدّل المتغيّر اليدويّة — كانت في الذاكرة فقط)،
**`v96_spatial_geometry_integrity.sql`**، **`v97_user_self_with_check.sql`**.

## نمط RLS fail-closed (مُقتبَس بإيجاز)

العزل ثلاثيّ الطبقات: التطبيق يتّصل بدور مقيّد `sahool_app` (NOSUPERUSER NOBYPASSRLS)؛ الترحيلات
وحدها بالمالك المُمتاز؛ المهامّ الخلفيّة العابرة للمستأجرين بدور `sahool_jobs` (BYPASSRLS). يُطبَّق
`v9_rls_force_all.sql` **أخيراً** ليفرض RLS على كلّ الجداول بعد إنشائها (`MANIFEST.txt:47-49`)،
ثمّ التغطية الديناميكيّة `v56_rls_dynamic_all.sql` (catch-all لأيّ جدول يحمل `tenant_id` بلا سياسة)
و`v70_rls_with_check_propagate.sql` (يمنع الكتابة العابرة للمستأجرين عبر `WITH CHECK`). أيّ غياب
سياق ⇒ صفر صفوف (fail-closed) لا تسرّب.
