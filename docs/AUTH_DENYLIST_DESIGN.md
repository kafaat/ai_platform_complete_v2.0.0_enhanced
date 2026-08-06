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
