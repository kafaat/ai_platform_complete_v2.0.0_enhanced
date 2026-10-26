// SAHOOL — features/farm_book/presentation/farm_book_text.dart
// تسميات دفتر المزرعة العربيّة، تنسيق المبالغ، تحقّق إدخال المبلغ (يقبل ٠-٩ و«٫»)،
// وترجمة رموز أخطاء simple_farm_book.py إلى رسائل يفهمها المزارع.
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/utils/formatters.dart';

/// تصنيفات المصروف (core/farm_ledger.py: LedgerKind + KIND_NAMES_AR).
const Map<String, String> kExpenseCategories = {
  'seed': 'بذور',
  'fertilizer': 'أسمدة',
  'pesticide': 'مبيدات',
  'labor': 'عمالة',
  'fuel': 'وقود',
  'water': 'ري',
  'equipment': 'معدّات',
  'transport': 'نقل',
  'other_expense': 'مصروف آخر',
};

/// تصنيفات الإيراد.
const Map<String, String> kIncomeCategories = {
  'harvest_sale': 'بيع المحصول',
  'subsidy': 'دعم/منحة',
  'other_income': 'دخل آخر',
};

/// تصنيف السداد كما يرسله الويب (SimpleFarmBookPage.tsx).
const String kPaymentCategory = 'debt_payment';

String categoryLabel(String code) =>
    kExpenseCategories[code] ??
    kIncomeCategories[code] ??
    (code == kPaymentCategory ? 'سداد دين' : code);

String entryTypeLabel(String type) => switch (type) {
  'expense' => 'مصروف',
  'income' => 'إيراد',
  'payment' => 'سداد دين',
  _ => type,
};

String paymentMethodLabel(String method) => switch (method) {
  'cash' => 'نقدي',
  'credit' => 'آجل',
  _ => method,
};

const Map<String, String> kPartyTypes = {
  'supplier': 'مورد',
  'customer': 'عميل (مشترٍ)',
  'both': 'مورد وعميل',
};

String partyTypeLabel(String type) => kPartyTypes[type] ?? type;

/// وحدة العملة بالعربيّة. ر.ي للريال اليمنيّ (كـfmtYer)، وغيرها برمزها.
String currencyUnitAr(String? currency) => switch (currency?.toUpperCase()) {
  null || 'YER' => 'ر.ي',
  'SAR' => 'ر.س',
  'USD' => 'دولار',
  final c => c,
};

/// مبلغ بعملته: «12,500.5 ر.ي». الأرقام غربيّة كبقيّة التطبيق والويب
/// (formatters.dart). null ⇒ «غير مقيس». السالب يُسبَق بعلامة LRM كي لا تنقلب
/// إشارته في سطر عربيّ.
String fmtMoney(num? amount, String? currency) {
  if (amount == null) return kNotMeasured;
  final n = fmtNumber(amount, decimals: 2);
  return '${amount < 0 ? '\u200E' : ''}$n ${currencyUnitAr(currency)}';
}

final RegExp _amountPattern = RegExp(r'^\d{1,16}(\.\d{1,2})?$');

/// يطبّع مبلغاً كتبه المستخدم بأيّ أرقام (٠-٩ / ۰-۹ / «٫» / فواصل آلاف) إلى نصّ
/// عشريّ يقبله الخادم (Decimal: 18 خانة، منزلتان). غير صالح ⇒ null.
String? normalizeAmount(String? raw) {
  if (raw == null) return null;
  final s = normalizeDigits(raw.trim()).replaceAll(' ', '');
  if (!_amountPattern.hasMatch(s)) return null;
  final v = double.parse(s);
  if (v <= 0) return null;
  return s;
}

/// رسالة تحقّق حقل المبلغ، أو null إن كان صالحاً.
String? validateAmount(String? raw) {
  final text = normalizeDigits((raw ?? '').trim()).replaceAll(' ', '');
  if (text.isEmpty) return 'أدخل المبلغ';
  if (RegExp(r'^\d+\.\d{3,}$').hasMatch(text)) {
    return 'المبلغ يقبل منزلتين عشريّتين كحدّ أقصى';
  }
  if (!RegExp(r'^\d+(\.\d+)?$').hasMatch(text)) return 'أدخل مبلغاً صحيحاً';
  if (RegExp(r'^\d{17,}').hasMatch(text)) return 'المبلغ أكبر من المسموح';
  if (double.parse(text) <= 0) return 'المبلغ يجب أن يكون أكبر من صفر';
  return null;
}

/// رموز `detail` التي يرميها simple_farm_book.py ومعناها للمستخدم.
const Map<String, String> _detailAr = {
  'credit_requires_party':
      'البيع أو الشراء الآجل يحتاج تحديد المورد أو العميل.',
  'payment_must_be_cash': 'السداد يكون نقديّاً فقط.',
  'only_payment_can_settle_entry': 'السداد وحده يُسدِّد قيداً آجلاً.',
  'payment_cannot_be_a_reversal': 'لا يمكن عكس قيد سداد.',
  'payment_requires_party_and_settled_entry':
      'اختر الطرف والقيد الآجل المراد سداده.',
  'settled_entry_must_be_credit': 'القيد المختار للسداد ليس قيداً آجلاً.',
  'payment_party_or_currency_mismatch':
      'الطرف أو العملة لا يطابقان القيد الآجل المختار.',
  'payment_exceeds_remaining_debt':
      'المبلغ أكبر من المتبقّي على هذا القيد الآجل.',
  'reversal_cannot_also_settle': 'القيد العكسي لا يُسدِّد ديناً.',
  'reversed_entry_not_found': 'القيد الأصليّ غير موجود.',
  'cannot_reverse_a_reversal': 'لا يمكن عكس قيد عكسي.',
  'reversal_must_mirror_original':
      'القيد العكسي يجب أن يطابق القيد الأصليّ تماماً (النوع والدفع والمبلغ والطرف).',
  'entry_already_reversed': 'هذا القيد عُكس من قبل؛ لا يُعكس مرّتين.',
  'client_operation_id_payload_conflict':
      'أُرسلت هذه العمليّة سابقاً بقيم مختلفة. حدّث الدفتر وتحقّق قبل الإعادة.',
  'entry_constraint_conflict':
      'تعارض مع قيد محفوظ. حدّث الدفتر ثمّ أعِد المحاولة.',
  'farm_not_found_for_tenant': 'المزرعة غير موجودة في حسابك.',
  'season_not_found_for_tenant': 'الموسم غير موجود في حسابك.',
  'party_not_found_for_tenant': 'المورد أو العميل غير موجود في حسابك.',
  'receipt_document_not_found_for_tenant': 'مستند الإيصال غير موجود.',
  'month_must_be_yyyy_mm': 'صيغة الشهر غير صالحة.',
  'invalid_party_type': 'نوع الطرف غير صالح.',
  'reportlab_not_installed':
      'تصدير PDF غير مفعّل على الخادم حاليّاً. جرّب تصدير CSV.',
};

/// رسالة خطأ دفتر المزرعة: رمز خادم معروف ⇒ معناه، وإلّا رسالة ApiException
/// القياسيّة (عقد 503/403/401/404 لا يُستبدَل).
String farmBookErrorMessage(Object error) {
  final e = ApiException.from(error);
  final d = e.detail;
  if (d is String && _detailAr.containsKey(d)) return _detailAr[d]!;
  return e.messageAr;
}
