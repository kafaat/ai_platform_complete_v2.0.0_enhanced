# Element84: جرد قرائي لمستأجر مأذون

`ELEMENT84-LEGACY-PRODUCTS-UNINVENTORIED-01` — open. لا ينفذ هذا runbook في المهمة الحالية؛ يلزم تفويض المالك للبيئة والمستأجر المحددين وبيانات اعتماد منفصلة.

## شروط التشغيل

سجل التفويض واسم البيئة وUUID المستأجر وSHA من `git rev-parse HEAD` ونسخة الأداة. راجع `scripts/diagnostics/element84_legacy_inventory.py:87-215`. لا تصل بقاعدة غير محلية قبل التفويض المستقل. لا يُسجل DSN أو سر في الأدلة.

الدور يحتاج CONNECT على القاعدة وUSAGE على schema وSELECT على الجداول الستة: raster_assets، raster_registry، backfill_run_items، backfill_runs، raster_batch_jobs، distributed_raster_jobs. يجب أن يكون NOSUPERUSER وNOBYPASSRLS، بلا منح كتابة أو ملكية أو صلاحية SET ROLE إلى دور أعلى. تفحص الأداة FORCE RLS وسياسة المستأجر؛ لا تتجاوز فشلها بمنح صلاحيات أوسع. تستخدم معاملة readonly وrepeatable_read وتضبط app.current_tenant وstatement_timeout=30s.

## الأمر الدقيق

بعد توفير `SAHOOL_INVENTORY_DATABASE_URL` من مخزن أسرار مأذون، وتعيين `AUTHORIZED_TENANT_ID` و`INVENTORY_OUTPUT` إلى ملف جديد غير موجود:

```bash
umask 077
python3 scripts/diagnostics/element84_legacy_inventory.py --tenant-id "$AUTHORIZED_TENANT_ID" --limit 10000 --output "$INVENTORY_OUTPUT"
```

احفظ stdout وstderr بعد فحص خلوهما من أسرار، ورمز الخروج الفعلي، وSHA الأداة وsha256 الناتج مع التفويض. يكتب الملف حصرياً بصلاحية 0600؛ لا تستبدل ملفاً سابقاً.

## قراءة النتيجة

- exit 0 وsnapshot_complete=true: اكتمال اللقطة المرئية لهذا الدور والمستأجر فقط؛ لا يعني قبول إنتاج أو اكتمال كل التاريخ.
- exit 3: truncated؛ ليست لقطة كاملة. آلية LIMIT+1 تكشف الاقتطاع. row_count_lower_bound حد أدنى لكل مصدر، ولا يجوز تحويله إلى إجمالي منتجات فريدة.
- exit 2: رفض أو فشل؛ لا تفسره على أنه صفر منتجات. احتفظ بالسبب وتوقف دون تجاوز RLS.
- provider=unknown والقيم null تبقى مجهولة. algorithm_version ليست processing_version. قد تتكرر هوية المنتج عبر المصادر الستة.
- غياب HTTP422 محفوظ لا يثبت عدم وقوعه. الجرد لا يثبت فساد القياسات ولا يصلحها.

## مستويات القبول

محلي: مراجعة الأداة وrunbook فقط. CI: لم تقاس بهذه الإضافة. staging والإنتاج: غير مقيسين ومحجوبان بالتفويض وبيانات الاعتماد. تبقى الفجوة open حتى جرد مأذون ودليل محدود النطاق؛ لا إعادة بناء للأداة الموجودة.
