# الجولة السادسة — معالجة دين lint + صحّة الحاويات (15 وكيلًا متوازيًا)

نُفِّذ بـ**15 وكيلًا متوازيًا** على مسارات منفصلة (لا تعارض)، مع تحقّق شامل
أجراه المنسّق بعد اكتمالهم.

## النتيجة الكبرى: ruff 3265 → 0 (All checks passed)
انخفاض **100%** للأخطاء القابلة للإصلاح الآمن + الأخطاء الحقيقية. الباقي
الوحيد (67×UP042 `class X(str, Enum)`) **تُرك عمدًا** وأُضيف تجاهله في
`ruff.toml` موثّقًا: StrEnum يغيّر دلالة `str(member)`/التسلسل وقد يكسر
JSON/Pydantic/DB بصمت.

## أخطاء حقيقية اكتشفتها الوكلاء وأُصلحت (ليست مجرّد تنسيق)
| الخطأ | الملف | الإصلاح |
|------|------|---------|
| F821 `Awaitable` غير مستورد | api/command_store.py | أُضيف للاستيراد |
| F821 `op` غير معرّف (خطأ منطقي) | core/offline_first.py | `self._queues[tenant_id]=kept` |
| **F821 `tenant_id` غير معرّف ×6** | mcp_servers/market_server.py | `tenant_id=args.get("tenant_id")` في tool_get_market_price/tool_get_price_trend (مطابق للأدوات الشقيقة) |
| F821 `l` مُعلّق (مرجع خاطئ) | tests_v9/test_roadmap_phase23.py | `nc["principle_ar"]` |
| F841 متغيّرات ميتة | core (×2)، api decision_engine/temporal_arbitration، auth | حُذفت بأمان |
| ~70× B904 (سلسلة الاستثناءات) | عبر الخدمات | `raise … from e/err/None` |
| ~10× B905 (`zip` strict) | عبر الخدمات | `strict=True/False` حسب الثبات |
| B017/B011/B007 | اختبارات | تضييق/تصحيح |
| تَموضُع imports فوق shebang/docstring | guardrails, edge-inference, mcp, bots, telegram | إعادة ترتيب صحيحة |

### خطأ حرج اكتشفه التحقّق النهائي (سابق، لا من الوكلاء)
**`raster-service/main.py` لم يكن يُقلع إطلاقًا**: `_TRANSPARENT_PNG =
bytes.fromhex("…")` بطول **فردي (137 خانة)** ⇒ `ValueError` عند الاستيراد ⇒
تعطّل الخدمة كاملةً. استُبدلت ببلاطة PNG 1×1 شفّافة صحيحة (68 بايت، CRC سليمة،
مُولّدة عبر zlib). الآن تستورد الخدمة.

## صحّة الحاويات (مشكلة لقطة الشاشة: qdrant/nats/ollama/redis تفشل)
شُخّصت ثابتًا (لا Docker daemon) وأُصلحت في `docker-compose.{fixed,unified,v9,light}.yml`:
| الخدمة | الجذر | الإصلاح |
|--------|------|---------|
| **qdrant** | صورة distroless بلا curl/shell ⇒ healthcheck يفشل دومًا ⇒ سلسلة `service_healthy` تنهار (هذا سبب اللقطة) | إزالة healthcheck المعطوب + التابعون → `service_started` |
| **nats** | healthcheck على المنفذ/الأداة الخطأ | `wget` على منفذ المراقبة 8222 `/healthz` + `start_period` |
| **ollama** | لا curl في الصورة | `["CMD","ollama","list"]` + `start_period 60s` |
| **redis** | **مفتاح `command:` مكرّر أسقط `--requirepass`** (يعمل بلا مصادقة!) + healthcheck NOAUTH | دمج command واحد + `redis-cli -a $$REDIS_PASSWORD ping` |

## التحقّق النهائي (المنسّق، بعد اكتمال كل الوكلاء)
```
ruff (كامل) .......... 0 (كان 3265)      pytest الكامل ........ 244/0/0
verify_review_fixes .. 23/23             RLS enforcement(sh) .. 10/10
services functional .. 10/10             auth e2e ............. 10/10
platform smoke+e2e ... 13/13             استيراد الخدمات ...... 10 ✓ / 8 تبعيّات خارجيّة / 0 كسر
py_compile ........... كل الملفات المُغيّرة ✓
```
لا انحدار: التنسيق المتوازي وإزالة الاستيرادات والإصلاحات لم تكسر شيئًا.
