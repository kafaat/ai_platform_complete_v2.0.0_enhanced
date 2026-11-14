# ربط قائمة إبطال JWT بالمنصّة (H1) — تصميم النشر

يعالج **H1** من مراجعة الجولة ٢: تسجيل الخروج/تعطيل المستخدم لا يُبطِل الوصول لنقاط
بيانات المنصّة (توكنات 24س بلا فحص `jti`).

## ما هو جاهز (مُختبَر offline)
`core/jwt_denylist.py` — نواة الإبطال: `is_token_revoked(backend, jti)` **fail-open**
+ `RedisDenylist`/`InMemoryDenylist` بنفس مفتاح خدمة auth `sahool:jti:revoked:{jti}`.
(٧ اختبارات.) خدمة auth **تُبطِل أصلاً** على logout (`revoke_jti`).

## خطوة النشر (تحتاج Redis حيّاً + اختبار تكامل — لذا ليست في هذا الـPR)
المنصّة (`api/main.py`) لا تستورد Redis حاليّاً. الربط:

1. **عميل Redis متزامن** في المنصّة (FastAPI يشغّل التبعيّات المتزامنة في threadpool،
   فالنداء الحاجز آمن):
   ```python
   import redis  # redis-py

   _denylist = RedisDenylist(redis.from_url(os.environ["REDIS_URL"], socket_timeout=0.2))
   ```
2. **في `get_current_user`** بعد فكّ التوكن (إضافيّ، غير كاسر):
   ```python
   from core.jwt_denylist import is_token_revoked

   if is_token_revoked(_denylist, payload.get("jti")):
       raise HTTPException(401, "Token revoked")
   ```
   - توكن بلا `jti` يمرّ (توافق خلفي). توكن مُبطَل ⇒ 401. Redis ساقط ⇒ fail-open
     (يُسمَح، يُسجَّل) — لا قفل جماعي.
3. **(اختياريّ، أقوى) `is_active`**: لإبطال فوريّ عند تعطيل المستخدم دون انتظار logout،
   خزّن `sahool:user:disabled:{user_id}` عند التعطيل وافحصه بنفس النمط.
4. **التحقّق:** اختبار تكامل: سجّل دخول → استدعِ نقطة بيانات (200) → logout → نفس
   التوكن (401). يلزم Redis حيّ مشترك بين auth والمنصّة.

## لماذا لم يُربَط الآن؟
الربط يضيف تبعيّة Redis لمسار المصادقة (كلّ طلب) ولا يُتحقَّق منه إلّا بـRedis حيّ +
خدمتَي auth/platform معاً. شحنه أعمى يخاطر بمسار المصادقة للمنصّة كلّها. النواة جاهزة
ومُختبَرة؛ الربط خطوة نشر بسطرين موثَّقة أعلاه.

## ملاحظة TTL
لتقليص نافذة التعرّض، اخفض `JWT_EXPIRY_HOURS` (المنصّة، حاليّاً 24) — قرار UX/أمن.

## قرار المالك (2026-11-14): القراءة الآمنة تستمرّ أثناء انقطاع مخزن الإبطال

> ما سبق تاريخيّ: «fail-open» في الخطوة ٢ لم يعد السياسة. C-02 جعل المنصّة fail-closed في الإنتاج،
> و#1427 جعل auth يردّ 503 على **كلّ** طلب تعذّر فحص إبطاله. هذا القسم هو السياسة الحاليّة.

**القرار:** ما دام مخزن الإبطال (Redis) ساقطاً **أثناء التشغيل**، تستمرّ القراءات الآمنة ويبقى
رفض الكتابة.

| حالة الإبطال | GET / HEAD / OPTIONS | POST / PUT / PATCH / DELETE، أو مستدعٍ مباشر بلا طلب |
|---|---|---|
| مُبطَل مُثبَت (jti أو أرضيّة المستخدم)، وإن تعذّر الفحص الآخر | 401 | 401 |
| مجهولة: المخزن رمى استثناءً | يمضي + WARNING `REVOCATION-STORE-UNAVAILABLE-READ-ALLOWED` | 503 |
| سليم وغير مُبطَل | يمضي | يمضي |

- **auth:** `services/auth/session_tokens.py::session_revoked(…, request=)`، والسياسة نفسها في كلّ
  بيئة. `main.get_current_user` يمرّر الطلب فقط. مساراتُ الكتابة التي تُبطِل الجلسات (تغيير الدور،
  التعطيل) تبقى 503: هي `PATCH`، ولها رفضُها الخاصّ أيضاً حين يغيب المخزن أو يرفض الكتابة.
- **المنصّة:** `core/jwt_denylist.py::unverifiable_allows(method, production=)`. الفعل الآمن يمضي في
  كلّ بيئة؛ غيره 503 `token_revocation_unverifiable` في الإنتاج، وخارج الإنتاج يُسمَح مع تحذير كما
  كان منذ C-02 (لم يغيّره هذا القرار).
- **الثابتان مشتركان بالقيمة لا بالاستيراد:** `SAFE_METHODS` و`READ_ALLOWED_REASON` معرَّفان في
  الخدمتين (لا تستورد إحداهما الأخرى)، ويثبّت تطابقَهما
  `test_safe_method_constants_are_the_same_in_auth_and_the_platform`.
- **المستدعي بلا طلب** (`mfa_enrollment.user_for` في auth، مصافحة WebSocket في
  `routers/notifications.py` بالمنصّة) لا فعل له، فلا يُعامَل قراءةً.
- **لا عدّاد قائم** لفشل فحص الإبطال في الخدمتين، فالإشارة الوحيدة هي سطر WARNING برمز السبب.
  عدّادٌ جديد قرارُ مراقبةٍ منفصل.

**GET لا يكفي — المسارات الصارمة (مراجعة #1449):** فعلُ GET وحده لا يجعل الطلب قراءةً آمنة. ثلاثة
أصناف تُرفَض بـ503 وإن كان الفعل GET، ما دام الإبطال مجهولاً:

1. **بوّابات nginx `auth_request` في auth.** الطلب الفرعيّ دائماً GET، لكنّه يُجيز طلباً آخر:
   - `GET /v1/auth/edge-sign` يوقّع شهادة HMAC لـ`POST /api/v1/seasons/{id}/accept`، فلا يوقّع أبداً
     والإبطال مجهول (`session_tokens.refuse_unknown_revocation(request)`).
   - `GET /v1/auth/verify` (`/_auth_verify`) يُجيز ما أرسله العميل إلى nginx أيّاً كان فعله. يُجيب
     فقط إن أعلن nginx فعلاً آمناً في `X-Original-Method`؛ فعلُ كتابة أو غيابُ الترويسة ⇒ 503.
     nginx يضبطها في كلّ `location = /_auth_verify` (`nginx/nginx.v9.conf` و`frontend/nginx.conf`)
     بـ`proxy_set_header X-Original-Method $request_method;`: `$request_method` في الطلب الفرعيّ هو
     فعلُ الطلب الرئيسيّ، و`proxy_set_header` يستبدل أيّ قيمة أرسلها العميل (مقيسٌ على nginx حقيقيّ:
     POST بترويسة مزوّرة `GET` وصل auth بـ`X-Original-Method: POST`). بوّابةٌ جديدة لا تضبطها
     تُرفَض في الانقطاع، لا تُفتَح.
2. **مسارات المنصّة المُبوَّبة بصلاحية غير عرض.** `require_permission` صارمٌ افتراضيّاً لكلّ صلاحية
   لا تنتهي بـ`:view` (`jwt_denylist.strict_revocation_for`): إدارة، تنفيذ، موافقة، منصّة. مثالُه
   `GET /api/v1/admin/break-glass/{token}/fields` (`PLATFORM_MANAGE`: يقرأ مستأجِراً آخر ويحدّث
   `access_count`).
3. **GET بأثرٍ جانبيّ تحت صلاحية عرض** يُعلِن صرامته: `require_permission(…, strict_revocation=True)`.
   مثالُه `GET …/prescriptions/{id}/export` (يفحص `EQUIPMENT_MANAGE` داخليّاً ويُدرِج
   `machinery_export_artifacts`).

الآليّة: حين تُمرَّر قراءةٌ والإبطال مجهول يُعلَّم الطلب (`request.state.revocation_unknown` في auth،
`revocation_unverifiable` في المنصّة)، والمسار الصارم يقرأ العلامة فيرفض. في المنصّة يسري الرفض في
الإنتاج وحده، كبقيّة سياستها (C-02).

**القاعدة لكلّ مسار GET جديد:** إن كان يكتب (INSERT/UPDATE/DELETE، عدّاد، أثر)، أو يُجيز طلباً آخر،
أو يتطلّب صلاحية غير `:view`، فهو صارم. المسح الذي أُجري لهذه المراجعة (معالجات GET في
`services/sahool-platform` والدوالّ التي تستدعيها داخل وحدتها حتّى ثلاث قفزات، بحثاً عن كتابة SQL أو
فحص صلاحية غير عرض) لم يجد غير المسارين أعلاه، و`GET /api/v1/lab/samples` الذي يفحص
`INSPECTION_REVIEW` ليحسب علامة «يحقّ له الاعتماد» دون أن يكتب شيئاً. المسح لا يرى كتابةً عبر وحدةٍ
أخرى، فالقاعدة تبقى مسؤوليّة كاتب المسار.

**ما لم يتغيّر — الإقلاع:** Redis غائبٌ أو لا يُجيب عند الإقلاع في الإنتاج يرفض الإقلاع في
الخدمتين (#408): ذلك خطأ نشر لا انقطاع، والسماح بالقراءة للانقطاع أثناء التشغيل وحده. خارج الإنتاج:
auth يُقلِع بـ`_redis = None` فتُتخطّى الفحوص (لا 503 ولا 401)، والمنصّة تُقلِع بذاكرة داخل العمليّة.

**المخاطرة المتبقّية (مقبولة بالقرار):** توكنٌ مُبطَل (خروج، تعطيل، تغيير كلمة المرور أو الدور) يستطيع
**القراءة** حتّى يعود المخزن، ومحدودةٌ بعمر التوكن: `JWT_EXPIRE_MINUTES` في auth و`JWT_EXPIRY_HOURS`
في المنصّة (auth: 60 دقيقة افتراضيّاً؛ المنصّة: 24 ساعة، فنافذتها أوسع). يخفّفها في auth أنّ مسارات إدارة الفريق
(`GET /v1/auth/users`) تتحقّق من العضويّة الفعّالة في Postgres لا من التوكن وحده، فمالكٌ عُطِّل يبقى
403. ولا تخفيف مماثلاً في كلّ قراءات المنصّة.

**الإثبات:** `tests_v9/test_auth_revocation_outage_read_policy.py` و
`tests_v9/test_platform_revocation_unverifiable_fail_closed.py` (وحدة)،
`tests_v9/test_auth_admin_authz_live_pg_redis.py::test_unreachable_redis_lets_get_users_through_scoped_to_the_callers_tenant`
(Postgres وRedis حيّان)، و`tests_v9/test_jwt_revocation_same_redis.py` (redis-server حقيقيّ يُوقَف).
