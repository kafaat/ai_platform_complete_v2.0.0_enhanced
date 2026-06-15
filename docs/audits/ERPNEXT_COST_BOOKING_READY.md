# تهيئة ERPNext push_field_cost للربط (أفضل الممارسات)

بحثٌ في وثائق Frappe/ERPNext الرسميّة، وتهيئة النظام للربط دون فبركة حسابات.

## أفضل الممارسات المطبّقة (من الوثائق الرسميّة)
1. **المصادقة**: Frappe token = `api_key:api_secret` في رأس
   `Authorization: token <key>:<secret>` — نظامك يطبّقها بالضبط ✓
2. **قيد اليوميّة المتوازن**: كلّ Journal Entry يحتاج سطرين accounts[] على
   الأقلّ، المجموع المدين = الدائن (شرط Frappe الإلزامي) — مطبّق ✓
3. **ربط cost center**: للمحاسبة التحليليّة لكلّ حقل — مدعوم (اختياري) ✓
4. **الحسابات خاصّة بكلّ تثبيت**: لا تُفبرك — تُضبط عبر env ✓

## ما كان وما صار
**قبل**: push_field_cost = NotImplementedError دائماً (رفض صادق لكن غير قابل
للتفعيل).
**بعد**: يبني Journal Entry متوازناً فعليّاً **عند ضبط الحسابات**؛ يبقى
NotImplementedError صادقاً **فقط** عند غيابها (لا فبركة، لا تراجع عن الصدق).

## التهيئة (env vars جديدة)
```bash
ERPNEXT_URL=https://erp.your-domain
ERPNEXT_API_KEY=<من User → API Access → Generate Keys>
ERPNEXT_API_SECRET=<السرّ المُولّد>
# ربط الحسابات (إلزامي لتفعيل push_field_cost — من دليل حسابات تثبيتك):
ERPNEXT_EXPENSE_ACCOUNT="Farm Operating Expenses - SAHOOL"  # مدين
ERPNEXT_CREDIT_ACCOUNT="Cash - SAHOOL"                       # دائن
ERPNEXT_COMPANY="SAHOOL Agriculture"                         # إلزامي
ERPNEXT_COST_CENTER="Al-Jawf Fields - SAHOOL"               # اختياري (تحليلي)
```

## البنية المبنيّة (Journal Entry)
- voucher_type=Journal Entry، posting_date، company، user_remark
- accounts[]: سطر مدين (expense_account) + سطر دائن (credit_account)،
  كلاهما بنفس المبلغ ⇒ متوازن (مدين=دائن)
- cost_center على كلّ سطر إن ضُبط
- تحقّق المدخلات: amount موجب إلزامي (ValueError إن لا)

## التحقّق (مُختبَر منطقيّاً)
- 675/675 roadmap (+5) · 0 خطأ
- بلا حسابات → NotImplementedError صادق ✓
- amount=0 → ValueError ✓
- القيد متوازن (مدين=دائن=المبلغ) ✓
- مصادقة token صحيحة ✓

## ملاحظة صدق
بحثتُ الوثائق الرسميّة (Frappe REST API + Journal Entry docs). هيّأتُ الربط
بأفضل ممارسة: account mapping عبر env (لا hardcode)، قيد متوازن، مصادقة token.
**لم أتراجع عن الصدق**: بلا الحسابات الإلزاميّة يبقى NotImplementedError —
لأنّ Frappe يرفض قيداً بلا حسابات صحيحة، وفبركتها تُنتج قيوداً محاسبيّة خاطئة
(أخطر من عدم الإرسال). التحقّق منطقي (لا أملك ERPNext حيّاً)؛ الاختبار الكامل
على جهازك: اضبط الحسابات الأربعة، أرسِل تكلفة، وتأكّد من ظهور Journal Entry
متوازن في Accounting. **حذار**: ابدأ بحساب اختبار (sandbox) قبل الإنتاج —
القيود المحاسبيّة في v13+ غير قابلة للتعديل (immutable ledger).
