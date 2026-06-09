# الجولة السابعة — smoke tests + بناء الحاويات

## Smoke tests للخدمات — `tests_v9/smoke_services.py`
يستورد تطبيق كل خدمة عبر `TestClient` ويتحقّق من `/healthz`، معزولًا كلًّا في
عمليّة فرعيّة (تفاديًا لتضارب سجلّ Prometheus/الوحدات).

**النتيجة: 15 HEALTHY · 1 skip · 0 FAIL**
```
✓ auth  ✓ soil-service  ✓ guardrails  ✓ vegetation  ✓ supervisor
✓ raster-service  ✓ weather-service  ✓ indicators  ✓ odoo-bridge
✓ agriai-engine  ✓ actuator  ✓ edge-inference  ✓ tts-service
✓ video-processor  ✓ market-mcp
~ local-ai-rag  (skip: langchain ثقيل، غير مثبّت في بيئة المساعد فقط)
```

### أخطاء حقيقية اكتشفها الـsmoke وأُصلحت
1. **`indicators-service` بلا `main.py`** — مجلّد فيه `Dockerfile/__init__.py/
   requirements.txt` فقط، لكن `CMD ["uvicorn","main:app"]` ⇒ الحاوية تدخل
   **crash-loop** عند الإقلاع (لا وحدة main). أُنشئ `main.py` stub صحّي
   (FastAPI + /healthz + /readyz) كي تُقلع الحاوية «صحّيّة» بصدق (المنطق
   الفعلي في sahool-platform/api، موثّق).
2. (من جولة سابقة، تأكّد هنا) **`raster-service`** كان يفشل بـ`bytes.fromhex`
   ⇒ الآن يُقلع ✓.

## بناء الحاويات
- **dockerd**: شُغِّل بنجاح (docker-in-docker) داخل بيئة المساعد.
- **سحب صور الأساس محظور** بسياسة شبكة البيئة: `docker pull python:3.11-slim`
  ⇒ **403 Forbidden** من Docker CDN. لذا البناء الكامل متعذّر هنا؛ أُثبت أن
  الفشل يقع **حصراً** عند `FROM python:3.11-slim` (تحميل تعريف Dockerfile
  وسياق البناء ينجحان) ⇒ الـDockerfiles سليمة بنيويًّا.
- **تحقّق ثابت بديل (كله ناجح):**
  - `docker compose config` على الملفات الستّة القابلة للتشغيل: **كلها صحيحة**
    بعد الإصلاحات أدناه.
  - مصادر `COPY` في الـ21 Dockerfile: موجودة (التحذير الوحيد `--from=builder
    /app/dist` إيجابي كاذب لبناء متعدّد المراحل).

### أخطاء حقيقية في docker-compose اكتشفها `compose config` وأُصلحت
| الملف | الخطأ | الإصلاح |
|------|------|---------|
| fixed.yml | مفتاح `start_period` **مكرّر** (سطرَا 237/238) ⇒ YAML غير صالح | حُذف التكرار |
| unified.yml & light.yml | حجم `edge_data` **مُستخدَم بلا إعلان** (edge-inference) | أُعلِن في `volumes:` |
| unified.yml | حجم `odoo-filestore` مُستخدَم بلا إعلان | أُعلِن |
| unified.yml | `sahool-odoo` يعتمد على خدمة **`sahool-postgres` غير معرّفة** | → `postgis` (الاسم الصحيح) |

> ملاحظة: `docker-compose.odoo-snippet.yml` مقتطف (fragment) لا ملفّ مستقل،
> فلا يُتوقّع أن يُصادق وحده.

## التحقّق
```
smoke_services ........ 15 HEALTHY / 1 skip / 0 FAIL
docker compose config . 6/6 ملفات صحيحة
ruff (كامل) ........... 0 (All checks passed)
pytest --collect ...... 295 تُجمَّع بلا أخطاء
```
