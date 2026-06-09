# ADR-0001: تجريد مزوّد ERP (Odoo / ERPNext / none)

## الحالة
مقبول — مُطبَّق (services/odoo-bridge/erp_provider.py)

## السياق
احتاج النظام مرونة في مزوّد ERP: Odoo فشل في البناء، وERPNext بديل مفتوح
المصدر، وبعض النشرات لا تحتاج ERP إطلاقاً.

## القرار
واجهة `ERPProvider` موحّدة + 3 تطبيقات (Odoo/ERPNext/Null)، يُختار المزوّد
بمتغيّر `ERP_PROVIDER`. odoo-bridge يعمل مع أيّ مزوّد (تبعيّة Odoo required:false).

## العواقب
- (+) تبديل المزوّد بلا تغيير كود
- (+) النظام يعمل بلا ERP (NullProvider → farm_ledger محلّي)
- (−) واجهة موحّدة تعني قاسماً مشتركاً (ميزات ERP الخاصّة تحتاج تمديداً)
