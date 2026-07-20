# رَنبوك التشغيل — SEASON-RECORD-ENTRY-01 (بوّابة إدخال سجلّ الموسم)

> **قابل للنسخ من الشاشة.** كلّ كتلة أوامر مُصمَّمة للصقّ المباشر في صدفة المُشغّل على بيئة staging/الإنتاج.
> المصدر الوحيد للحقيقة الأمنيّة: `SEASON_EDGE_HMAC_KEY` **فئة B** (سرّ من مدير الأسرار، لا في compose).
> نموذج فشل‑مغلق: أيّ متغيّر ناقص �⇒ الميزة معطّلة بصدق (404/503)، لا قبول صامت.

الحالة: 3a + 3b (auth edge-sign + nginx) + 3c (الواجهة) مبنيّة ومدموجة على `main`. البراهين الحيّة أدناه
(§3) هي الوحيدة التي تتطلّب stack كامل مُشغَّلاً — تُنفَّذ **مرّة** عند أوّل إقلاع كامل، وتُوثَّق نتيجتها.

---

## 1. تفعيل الميزة (متغيّرات البيئة)

في `.env` لبيئة staging/الإنتاج (لا في compose — الأسرار تُحقَن):

```bash
# راية التفعيل (افتراضيّ 0 ⇒ النقاط الستّ تعيد 404)
SEASON_ENTRY_ENABLED=1

# توكن قناة المواسم (خدمة‑لخدمة؛ nginx يحقنه upstream نحو scout-ingest). سرّ عشوائيّ ≥32 محرفاً.
SEASON_ENTRY_SERVICE_TOKEN="$(openssl rand -hex 32)"

# مفتاح تصديق الحافّة HMAC — فئة B. يُشارَك بين auth (المُوقِّع) وscout-ingest (المُتحقِّق) فقط.
# لا يظهر في أيّ ملفّ compose. يُحقَن مباشرةً في بيئة الحاويتين عبر مدير الأسرار/الأوركستريتور.
SEASON_EDGE_HMAC_KEY="$(openssl rand -hex 32)"
```

> **حقن `SEASON_EDGE_HMAC_KEY` في الحاويتين فقط:** auth + scout-ingest. لا nginx، لا المنصّة.
> غيابه ⇒ `/auth/edge-sign` يعيد 503 و`accept` يرفض كلّ طلب بـ401 `edge_unattested` (الوضع الآمن).

إعادة تشغيل الحاويات المعنيّة لتطبيق المتغيّرات:

```bash
docker compose -f docker-compose.v9.yml up -d --no-deps \
  sahool-auth sahool-scout-ingest sahool-nginx
```

تحقّق سريع أنّ nginx استبدل `${SEASON_ENTRY_SERVICE_TOKEN}` في القالب (يجب ألّا يبقى حرفيّاً):

```bash
docker compose -f docker-compose.v9.yml exec sahool-nginx \
  sh -c 'grep -c "SEASON_ENTRY_SERVICE_TOKEN" /etc/nginx/nginx.conf'   # المتوقَّع: 0 (استُبدِل)
```

---

## 2. مسار الطلب (خريطة الثقة)

```
المتصفّح ──(كوكي sahool_at)──► nginx
  │
  ├─ /api/v1/seasons (عامّ)         ─► auth_request /_auth_verify ─► scout-ingest /internal/seasons*
  │        يحقن X-Tenant-Id الموثّق + X-Season-Entry-Token · يجرّد كلّ ترويسات الثقة من العميل
  │
  └─ /api/v1/seasons/{id}/accept   ─► auth_request /_auth_edge_sign ─► auth يوقّع HMAC مقيَّد الوجهة
           nginx يرفع X-User-Id/X-Roles/X-Edge-* من ردّ auth ويمرّرها ─► scout-ingest accept
           (scout-ingest يعيد التحقّق من طلبه هو — method/path/body — لا من ترويسة)
```

القانونيّة (`/internal/seasons...`) تأتي من مصدر واحد: `map $request_uri $season_canonical_path` —
نفس المتغيّر يُغذّي X-Canonical-Path لـauth **و** هدف proxy_pass، فيستحيل انحرافهما.

---

## 3. البراهين الحيّة (تُنفَّذ مرّة عند أوّل إقلاع كامل — لا يمكن إثباتها بوحدة)

> **حزمة جاهزة:** `scripts/e2e/season_gateway_live_gate.py` تُشغّل البراهين الثلاثة تلقائيّاً وتطبع
> PASS/FAIL + تلميحات (تخرج 0 عند نجاح الثلاثة):
> ```bash
> SEASON_BASE_URL=https://staging.sahool.ye \
> SEASON_COOKIE="sahool_at=<جلسة owner/expert>" \
> SEASON_SID="<uuid موسم مسودّة بمرفق دفتر>" \
> python scripts/e2e/season_gateway_live_gate.py
> ```
> (البرهان (ب) يُحوّل الموسم accepted — استخدم موسماً مخصَّصاً للاختبار.) الأوامر اليدويّة أدناه للتشخيص.

> تُدرَج ضمن قائمة تشغيل المالك بجانب PROD-01→07 لـirr_f01. البرهان المؤجَّل بلا موعد يموت صامتاً —
> لذا هذه المهمّة مرقّمة (#225) وتُقفَل فجوة `SEASON-EDGE-LIVE-PROOF` في الدماغ فور رصد الأخضر.

بيئة الاختبار: مستخدِم بدور `owner` أو `expert` (سلطة `season-reviewer`)، وموسم مسودّة له مرفق دفتر مرفوع
(جاهز للقبول). عرّف `COOKIE` = كوكي جلسة صالحة، و`SID` = معرّف الموسم، و`BASE` = أصل البوّابة.

```bash
BASE="https://staging.sahool.ye"        # أصل البوّابة
COOKIE="sahool_at=<جلسة owner/expert صالحة>"
SID="<uuid موسم مسودّة بمرفق دفتر>"
```

### ③ البرهان السلبيّ الأساسيّ — ترويسة X-Canonical-Path مزوَّرة من العميل لا تصل auth

يرسل العميل قبولاً **مع** ترويسة قانونيّة مزوَّرة تحاول توجيه التوقيع لمسار آخر. يجب أن يُطمَس التزوير
(nginx يكتب X-Canonical-* بنفسه) فيبقى التوقيع مقيَّداً بالمسار الحقيقيّ ⇒ **النتيجة المطلوبة: قبول سليم
أو 4xx، لكن لا تسريب ولا توقيع لمسار مزوَّر**. الإثبات الأدقّ: تزوير هويّة/تصديق مباشرةً ⇒ **401/deny**:

```bash
# (أ) هويّة/تصديق مزوَّران يُرسَلهما العميل مباشرةً على القبول ⇒ يُجرَّدان ⇒ auth يوقّع الحقيقيّ ⇒
#     السيناريو المهاجِم (بلا جلسة مُراجِع) يجب أن يفشل 401/403 لا أن يُقبَل.
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/api/v1/seasons/$SID/accept" \
  -H "X-Canonical-Path: /internal/seasons/OTHER/accept" \
  -H "X-User-Id: attacker" -H "X-Roles: owner,season-reviewer" \
  -H "X-Edge-Attestation: deadbeef" -H "X-Edge-Timestamp: 9999999999"
# المتوقَّع: 401  (الترويسات المزوَّرة جُرِّدت؛ لا توقيع صالح لهذا الطلب)
```

### ② البرهان المكمّل — تصديق مسار عامّ لا يُقبَل على القبول (تقيّد الطرفين بالداخليّ حيًّا)

يثبت أنّ المُوقِّع (auth) والمُتحقِّق (scout-ingest) يحسبان method/path من طلبهما هما لا من ترويسة:
تصديق صُكّ لمسار عامّ (GET/PATCH) لا يُعاد لعبه على `.../accept`.

```bash
# (ب) مُراجِع شرعيّ يقبل موسمه ⇒ 200 (المسار السعيد يعمل حيًّا)
curl -sS -o /dev/null -w 'accept-happy=%{http_code}\n' -X POST \
  "$BASE/api/v1/seasons/$SID/accept" -H "Cookie: $COOKIE"
# المتوقَّع: 200 · trust_status=accepted

# (ج) إعادة القبول على موسم مقبول ⇒ 409 (لا قبول مزدوج)
curl -sS -o /dev/null -w 'accept-again=%{http_code}\n' -X POST \
  "$BASE/api/v1/seasons/$SID/accept" -H "Cookie: $COOKIE"
# المتوقَّع: 409 season_already_accepted
```

### تسجيل النتيجة — ✅ مُنجَز (2026-07-20)

> **رُصِد `ALL PROOFS PASSED ✅` على staging** (فرع البناء `claude/code-review-34hO3`) — (أ) deny · (ب) 200 · (ج) 409. فجوة `SEASON-EDGE-LIVE-PROOF` مُقفَلة، المهمّة #225 مُغلَقة.

بعد رصد (أ)=401 و(ب)=200 و(ج)=409 على staging:
- حدّث قائمة تشغيل المالك: «SEASON-EDGE-LIVE-PROOF ✅ مرصود على staging <SHA>».
- أقفِل فجوة `sahool-brain/gaps/registry.md` → `SEASON-EDGE-LIVE-PROOF: closed`.
- أغلِق المهمّة #225.

---

## 4. استكشاف الأعطال

| العرَض | السبب المرجّح | الإصلاح |
|---|---|---|
| كلّ نقاط `/api/v1/seasons` تعيد 404 | `SEASON_ENTRY_ENABLED` غير 1 | اضبطها وأعِد تشغيل scout-ingest |
| القبول يعيد 503 `edge signing not configured` | `SEASON_EDGE_HMAC_KEY` غير مضبوط في auth | احقنه في بيئة auth (فئة B) |
| القبول يعيد 401 `edge_unattested` رغم مُراجِع | المفتاح غير متطابق بين auth وscout-ingest | تأكّد أنّ **نفس** القيمة في الحاويتين |
| النقاط تعيد 503 `SEASON_ENTRY_SERVICE_TOKEN` | التوكن غير مضبوط على scout-ingest | اضبطه (نفس قيمة nginx) |
| القبول يعيد 403 `reviewer_role_required` | المستخدِم ليس owner/expert | admin مستثنى عمداً — استخدم owner/expert |
| رفع الدفتر يعيد 415 | الملفّ ليس JPEG/PNG/PDF (magic bytes) | ارفع صورة/PDF صحيحة |
| القبول يعيد 422 `logbook_missing` | لا مرفق أو مرجع ميّت | ارفع الدفتر أوّلاً |
