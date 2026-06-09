# تدقيق فئات الأخطاء — فحص فعلي لا نظري

فحصتُ كلّ فئة من فئات الأخطاء التي حدّدتها المراجعة، على الكود فعليّاً (grep +
قراءة + تشغيل). النتيجة: **خطأ حقيقي واحد + فجوة بسيطة، والباقي مُعالَج أصلاً.**

## الأخطاء المُكتشَفة والمُصلَحة
### 🔴 ١. تسرّب موارد async (حقيقي — أُصلح)
`supervisor-agent` ينشئ `MCPClient` (عملاء httpx) لكن **بلا lifespan/shutdown**
→ الاتّصالات تتسرّب عند الإيقاف. `MCPClient.close()` موجود لكن **لا يُستدعى**.
- الإصلاح: أضفتُ `lifespan` handler يستدعي `mcp_client.close()` عند الإيقاف.

### 🟡 ٢. حدود إدخال ناقصة (فجوة بسيطة — أُصلحت)
`edge-inference`: `field_id: str` بلا حدود طول (إدخال نصّي غير محدود — خطر DoS بسيط).
- الإصلاح: قيّدتُه `min_length=1, max_length=64` (متّسق مع soil-service).

## الفئات المفحوصة — مُعالَجة أصلاً (لا خطأ)
| الفئة | الفحص | النتيجة |
|-------|-------|---------|
| Timeout gaps | httpx.AsyncClient | ✅ mcp_client له `Timeout(30,connect=5)` |
| Unbounded retries | while True (3) | ✅ كلّها MQTT listeners بـ`sleep(10)` backoff |
| Decision drift | 5 تشغيلات بنفس المدخل | ✅ deterministic تماماً (نفس القرار) |
| Event ordering | command_store + replay | ✅ `ON CONFLICT` + ترتيب `(occurred_at,seq,id)` |
| Unsafe deserialization | pickle/eval/yaml.load | ✅ لا شيء (`_gate_eval` اسم دالّة لا eval) |
| Silent failures | except: pass | ✅ 0 في الإنتاج (حملة سابقة) |
| Pydantic holes | NDVI/soil/edge models | ✅ SoilReading 7/8 مقيّد، edge بعد الإصلاح |
| Resource cleanup | aclose/close | ✅ MCPClient.close موجود + يُستدعى الآن |

## ملاحظة عن determinism (الأهمّ لمنصّة قرار)
شغّلتُ المايسترو 5 مرّات بنفس المدخل → نفس القرار بالكامل
(status=vigor_led, kc=1.15, salinity=0.440, stage=mid_peak). **لا decision
drift** — وهذا جوهري لموثوقيّة القرار الزراعي.

## التحقّق
- 640/640 roadmap (+5) · 0 خطأ
- circuit breaker 8/8 · router 14/14 (لا تراجع)
- اختبار error_audit_fixes يحرس الإصلاحات

## ما يحتاج جهازك (لم أزيّفه)
المراجعة اقترحت أدوات تحتاج تشغيلاً حيّاً — لا أستطيعها offline:
- `vulture` (dead code) · `radon cc` (تعقيد) · `mutmut` (mutation testing)
- `schemathesis` (fuzzing للـAPI — يحتاج خدمة حيّة + openapi)
- `trivy` (فحص الحاويات) · `pip-audit`/`safety` (ثغرات التبعيّات)
شغّلها على جهازك وارفع النتائج. خاصّةً `mutmut` — يكشف "وهم التغطية"
(اختبارات تغطّي السطور لا المنطق).

## ملاحظة صدق
فحصتُ **فعليّاً** لا نظريّاً: grep على الكود + قراءة السياق + **تشغيل**
المايسترو للتحقّق من determinism. الخطأ الحقيقي (تسرّب async) **مُصلَح ومُتحقَّق
منه بنيويّاً**. لم أدّعِ فحص ما يحتاج أدوات لا أملكها (mutmut/trivy/schemathesis)
— تركتُها لك صراحةً. معظم فئات المراجعة كانت **مُعالَجة أصلاً** (timeout/retry/
ordering/determinism) — أكّدتُ ذلك بالفحص لا بالافتراض.
