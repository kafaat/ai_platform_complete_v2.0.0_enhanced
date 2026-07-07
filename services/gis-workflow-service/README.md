# Sahool GIS Workflow Engine — الشريحة A: رِندرِر خرائط النشر

يحوّل مصفوفة قيم راستريّة + بيانات وصفيّة إلى **خريطة ورقيّة قابلة للنشر** (PNG @300dpi)
بعناصر خرائطيّة: عنوان · سهم شمال · scale bar مستدير · legend · caption (المصدر/التاريخ/
الإسقاط/الدقّة/الجودة).

## النطاق الحاليّ (صدق)
- **الشريحة A (V84):** `map_layout.py` (تخطيط نقيّ، بلا رسم) + `publication_map.py` (رِندرِر matplotlib Agg).
- **الشريحة B (V85):** `workflow_spec.py` (تحقّق/حلّ عقد + حظر المصادر الخارجيّة) +
  `self_checks.py` (فحوص required/quality حقيقيّة) + `run_bundle.py` (حزمة تشغيل كاملة
  `maps/data/reports/scripts/provenance` **لا-تُكتَب-فوقها**، `run_id` فريد، checksums،
  run_manifest نَسَب، ربط أدلّة اختياريّ). طبقة تشغيل/تدقيق فوق A/raster-service، لا محرّك بيانات.
- **غير مُنفَّذ بعد (شرائح لاحقة):** الشريحة C (خرائط النشرة الإقليميّة)، AOI trend متعدّد
  السنوات، backends بحثيّة (GEE/earthaccess — تبقى `active:false` حتّى اعتماد + تحقّق حيّ)،
  وأيّ نقطة HTTP.
- **لا ادّعاء:** الـcaption يعكس الحقول المُمرَّرة فقط؛ الناقص يُعرَض «غير متاح» (لا اختلاق
  مصدر/تاريخ/دقّة). بلا بيانات صالحة ⇒ `ValueError` (لا صورة فارغة مُضلِّلة).

## لماذا خدمة منفصلة؟
matplotlib/numpy تبعيّتان رسوميّتان ثقيلتان — تُعزَل هنا (requirements خاصّة) كي لا تُثقِل
`raster-service`/`api`. المصدر الأساسيّ للبيانات يبقى مخرجات `raster-service` (COG/`zonal_stats`)
لا اعتماداً خارجيّاً.

## الاختبار
```bash
pip install -r services/gis-workflow-service/requirements.txt pytest
PYTHONPATH=services/gis-workflow-service pytest services/gis-workflow-service/tests -q
```
`test_map_layout.py` نقيّ (بلا matplotlib)؛ `test_publication_map_render.py` دخانيّ
(`importorskip` — يُتخطّى بلا matplotlib).
