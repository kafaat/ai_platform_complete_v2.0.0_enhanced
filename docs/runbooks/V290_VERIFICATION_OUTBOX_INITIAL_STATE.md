# v290 — بداية صادرة التحقق من المعاينة

`SCOUTING-VERIFICATION-OUTBOX-INITIAL-STATE-01` · متابعة #1598 المدمج
عند `20bdffcc0d048a8cb36cd702cc45e96db9d6c68e`؛ أساس الفرع
`5b2194d62c5d188560fa55f68ddc5382801f300d` · 2026-11-25.

## السبب والنطاق

تحرس v289 انتقالات `scouting_verification_outbox` عند UPDATE، وتحرس عند INSERT
ربط التقييم والجسم والدليل. لكنها لا تفرض حالة البداية. لذلك يستطيع INSERT مباشر
ذو تقييم وجسم صحيحين أن يبدأ بـ`delivered` مع إيصال `{}` ومحاولات صفر، أو
`delivery_exhausted` بمحاولات صفر، أو `sending` بمحاولة تاسعة وحجز موجود.
هذه أمثلة على الفجوة، وليست صفوفًا ثبت وجودها في بيئة منشورة.

المصدر: [`v289`](../../migrations/v289_scouting_verification_bridge.sql)، تعريف
الجدول و`scouting_verification_delivery_guard` و`scouting_verification_delivery_insert_guard`.
كاتب التطبيق في [`fm_verification_store.py`](../../services/field-management-service/fm_verification_store.py)
يكتب الهوية والمحتوى ويعتمد قيم البداية الافتراضية، ولذلك لا يحتاج تعديلًا.

يحافظ الترحيل الأمامي [`v290`](../../migrations/v290_scouting_verification_initial_state.sql)
على بايتات v289. #1598 مدمج، وهناك [إيصال staging مثبت](https://github.com/kafaat/unified-local-lab/blob/710c4a3de74915b588c8c3292ecbe95ce9af94c8/docs/evidence/lab-receipts-20261116/1598-staging/receipt.json)
عن تطبيقها. نطاق ذلك الإيصال `DEPLOYMENT_LOGS_ONLY`؛ لا يثبت كتالوج staging الحي
ولا يثبت تطبيق v290.

## العقد الجديد

كل صف جديد يبدأ بالقيم الآتية:

| الحقل | القيمة الوحيدة المقبولة عند INSERT |
|---|---|
| `state` | `pending` |
| `attempts` | `0` |
| `lease_token` و`lease_until` | SQL NULL |
| `receipt` | SQL NULL؛ JSON `null` مرفوض أيضًا |
| `last_error` | SQL NULL |

الرفض: SQLSTATE `23514` مع `verification_delivery_initial_state_invalid`.
الحارس الجديد مستقل و`BEFORE INSERT`؛ تبقى حراس المحتوى والتحديث والحذف في v289.
إعادة تشغيل v289 لا تزيل الحارس الجديد. يستخدم الترحيل معاملة و`lock_timeout=15s`؛
غياب جدول الصادر يُفشل up، فلا تتحول قاعدة ناقصة إلى تطبيق ناجح بلا حارس.

**الصفوف القائمة تبقى كما هي.** لا UPDATE أو حذف أو تصفير للمحاولات أو الإيصالات.
وجود حالة تسليم نهائية حاليًا لا يكشف كيف أُدرج الصف أول مرة، ولذلك لا يجري الترحيل
تصحيحًا تاريخيًا بالتخمين. لا يتغير عقد HTTP أو حد المحاولات أو الحجز أو الرايات.

## التحقق المحلي

توجد الحالات في [اختبارات الجسر المضادة](../../tests_v9/test_scouting_verification_bridge_counterexamples_live_pg.py).
تُنشئ التقييم والجسم من رحلة المالك الحقيقية، ثم تزيل صف الصادر الخاص بالـfixture
في إعداد المالك فقط. كل محاولة INSERT مقاسة تجري بدور التطبيق المقيد مع المشغلات
فعّالة، ويتبع الرفض إدخال صحيح على المرجع نفسه. يمنع ذلك نجاحًا كاذبًا بسبب
`UNIQUE(assessment_id)` أو RLS أو جسم غير صحيح.

يشمل القبول الإدخال الافتراضي والصريح، الحالات التشغيلية غير الابتدائية، المحاولات
والحجز والإيصال والخطأ السابق، واستمرار حراس المحتوى والمستأجر. الضابط السالب يزيل
الحارس الجديد وحده داخل معاملة مرتجعة، ويثبت قبول الأمثلة الأصلية بدونه ثم استعادته.
تُقاس أيضًا إعادة up، وإعادة v289، وdown مرتين ثم up، مع بقاء صف مشروع سبق تسليمه.

يشغّل صاحب المختبر الاختبارات على قاعدة مؤقتة يملكها؛ يحتاج `TEST_DATABASE_URL`
لدور `NOSUPERUSER/NOBYPASSRLS` و`TEST_DATABASE_ADMIN_URL` لإعداد الاختبار فقط:

```bash
FIELD_TASK_CERTIFICATION_REQUIRED=1 pytest -v --tb=short \
  tests_v9/test_field_task_inspection_live_pg.py \
  tests_v9/test_scouting_verification_bridge_live_pg.py \
  tests_v9/test_scouting_verification_bridge_counterexamples_live_pg.py
```

يجب قراءة عدد الحالات المنفذة والتخطي من إيصال التشغيل. هذا الأمر وحده لا يشهد
بنجاحه، وإيصال محلي لا يمنح قبولًا لبيئة منشورة.

## القبول بعد تطبيق مأذون

هذه الوثيقة لا تمنح إذن تطبيق على staging أو production. بعد مراجعة التغيير ودمجه
وتطبيق البيان عبر مسار الترحيل المعتاد، يلزم قياس الحارس نفسه؛ عدّ الجداول والأعمدة
لن يكشف غيابه، إذ لا تنشئ v290 جدولًا أو عمودًا.

قراءة الكتالوج التالية تظهر الحارس والدالة الفعليين:

```sql
SELECT t.tgname, t.tgenabled,
       pg_catalog.pg_get_triggerdef(t.oid) AS trigger_definition,
       pg_catalog.pg_get_functiondef(t.tgfoid) AS function_definition
  FROM pg_catalog.pg_trigger AS t
 WHERE t.tgrelid = 'public.scouting_verification_outbox'::regclass
   AND t.tgname = 'scouting_verification_delivery_initial_guard'
   AND NOT t.tgisinternal;
```

المتوقع صف واحد، `tgenabled=O`، و`BEFORE INSERT`، وجميع شروط البداية الستة.
تُقارن دالة الحارس بالمصدر المثبت، مع التأكد من بقاء حراس v289 وسياسة المستأجر وFORCE RLS.
تحتاج رحلة الخدمة الفعلية قبولًا منفصلًا؛ قراءة الكتالوج لا تختبر التسليم عبر الشبكة.

**تداخل المصدر مع #1606:** عند رأسه
`d251a79fba3caa6790da142892e17fdadcd2bfef` يختار probe أعلى رقم ترحيل افتراضيًا
ثم الجداول التي ينشئها ذلك الملف. v290 لا تنشئ جداول، ولذلك يلزم اختيار
`PROBE_CATALOG_FILES=v289_scouting_verification_bridge.sql` لقراءة كتالوج جداول الجسر.
هذا استنتاج من [مصدر #1606 المثبت](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/blob/d251a79fba3caa6790da142892e17fdadcd2bfef/migrations/probe_schema_state.sh)،
وليس وصفًا لإعداد نُفذ على بيئة. لا يكفي وجود اسم الحارس وحده لإثبات محتوى دالته.

## التراجع

[`v290.down`](../../migrations/v290_scouting_verification_initial_state.down.sql)
يحذف الحارس الجديد ودالته فقط، ويقبل إعادة التشغيل حتى بعد غياب الجدول. لا يمس
صفوف الصادر أو حراس v289. لكنه يعيد ضمان INSERT إلى المستوى السابق الأضعف؛
سلامة البيانات من الحذف لا تعني استمرار منع البداية غير القانونية. لا يُستعمل
التراجع كطريقة لقبول إدخالات غير صحيحة في التشغيل العادي.
