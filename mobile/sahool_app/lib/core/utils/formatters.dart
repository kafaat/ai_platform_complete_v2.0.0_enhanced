// SAHOOL — lib/core/utils/formatters.dart
// تنسيق الأرقام والتواريخ والوحدات، وتحليل أرقام يكتبها المستخدم بأيّ لوحة.
//
// سياسة الأرقام: أرقام غربيّة (0-9) في العرض، مطابقةً للويب
// (frontend/src/lib/* يستعمل toLocaleString('en-US')) فلا يرى مستخدم رقمين
// مختلفين لنفس القيمة على المنصّتين. الإدخال يقبل الأرقام العربيّة-الهنديّة
// (٠-٩) والفارسيّة (۰-۹) وفاصلة عشريّة عربيّة (٫)، لأنّ لوحات المفاتيح العربيّة
// تكتبها افتراضيّاً — كانت `double.tryParse('٢٫٥')` تُرجع null فتُرسَل القيمة
// فارغة بصمت.
//
// الوحدات القانونيّة: هـ (هكتار)، مم، °م، كجم/هـ، ٪، ر.ي.
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';

const _arabicIndic = '٠١٢٣٤٥٦٧٨٩';
const _persian = '۰۱۲۳۴۵۶۷۸۹';

/// يحوّل الأرقام العربيّة-الهنديّة/الفارسيّة إلى غربيّة، و«٫» إلى «.»، ويحذف
/// فواصل الآلاف (٬ و,). لا يمسّ بقيّة الحروف.
String normalizeDigits(String input) {
  final b = StringBuffer();
  for (final ch in input.split('')) {
    final ai = _arabicIndic.indexOf(ch);
    final pi = _persian.indexOf(ch);
    if (ai >= 0) {
      b.write(ai);
    } else if (pi >= 0) {
      b.write(pi);
    } else if (ch == '٫') {
      b.write('.');
    } else if (ch == '٬' || ch == ',') {
      // فاصل آلاف — يُحذف
    } else {
      b.write(ch);
    }
  }
  return b.toString();
}

/// يحلّل رقماً بأيّ مجموعة أرقام. فارغ/غير صالح ⇒ null (لا صفر مُختلَق).
double? parseLocalizedNum(String? input) {
  if (input == null) return null;
  final s = normalizeDigits(input.trim());
  if (s.isEmpty) return null;
  return double.tryParse(s);
}

/// كـ[parseLocalizedNum] لكن لعدد صحيح فقط.
int? parseLocalizedInt(String? input) {
  if (input == null) return null;
  final s = normalizeDigits(input.trim());
  if (s.isEmpty) return null;
  return int.tryParse(s);
}

/// مُنسِّق إدخال يحوّل الأرقام العربيّة-الهنديّة أثناء الكتابة إلى غربيّة، فيعمل
/// `double.tryParse` وأيّ مُحقِّق قائم كما هو. يحلّ محلّ
/// `FilteringTextInputFormatter.digitsOnly` (الذي كان يحذف ٠-٩ العربيّة).
class LocalizedDigitsFormatter extends TextInputFormatter {
  const LocalizedDigitsFormatter({this.digitsOnly = false});

  /// true ⇒ تُحذف كلّ الحروف غير الرقميّة بعد التحويل (رموز MFA، أعداد صحيحة).
  final bool digitsOnly;

  @override
  TextEditingValue formatEditUpdate(
      TextEditingValue oldValue, TextEditingValue newValue) {
    var text = normalizeDigits(newValue.text);
    if (digitsOnly) text = text.replaceAll(RegExp(r'[^0-9]'), '');
    if (text == newValue.text) return newValue;
    return TextEditingValue(
      text: text,
      selection: TextSelection.collapsed(offset: text.length),
    );
  }
}

final NumberFormat _n0 = NumberFormat('#,##0', 'en_US');
final NumberFormat _n1 = NumberFormat('#,##0.#', 'en_US');
final NumberFormat _n2 = NumberFormat('#,##0.##', 'en_US');

/// نصّ القيمة غير المقيسة — موحّد في كلّ التطبيق.
const String kNotMeasured = 'غير مقيس';

/// رقم بحدّ أقصى [decimals] منازل عشريّة (0..2). null ⇒ «غير مقيس».
String fmtNumber(num? value, {int decimals = 1}) {
  if (value == null || (value is double && value.isNaN)) return kNotMeasured;
  final f = decimals <= 0 ? _n0 : (decimals == 1 ? _n1 : _n2);
  return f.format(value);
}

String _withUnit(num? value, String unit, int decimals) =>
    value == null ? kNotMeasured : '${fmtNumber(value, decimals: decimals)} $unit';

/// مساحة بالهكتار: «1.5 هـ».
String fmtArea(num? hectares, {int decimals = 1}) =>
    _withUnit(hectares, 'هـ', decimals);

/// مليمتر (مطر/ريّ): «12 مم».
String fmtMm(num? mm, {int decimals = 1}) => _withUnit(mm, 'مم', decimals);

/// درجة حرارة: «31 °م».
String fmtTempC(num? celsius, {int decimals = 0}) =>
    _withUnit(celsius, '°م', decimals);

/// إنتاجيّة: «4,200 كجم/هـ».
String fmtYieldKgHa(num? kgHa) => _withUnit(kgHa, 'كجم/هـ', 0);

/// كتلة بالكيلوغرام: «35 كجم».
String fmtKg(num? kg, {int decimals = 1}) => _withUnit(kg, 'كجم', decimals);

/// عملة يمنيّة: «12,000 ر.ي».
String fmtYer(num? riyal) => _withUnit(riyal, 'ر.ي', 0);

/// نسبة مئويّة. [value] بين 0 و100 ما لم يكن [fraction]=true (0..1).
String fmtPct(num? value, {bool fraction = false, int decimals = 0}) {
  if (value == null) return kNotMeasured;
  final pct = fraction ? value * 100 : value;
  return '${fmtNumber(pct, decimals: decimals)}٪';
}

const _monthsAr = [
  'يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو',
  'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر',
];

/// تاريخ بالتوقيت المحلّيّ: «5 مارس 2026». null ⇒ «—».
String fmtDate(DateTime? value) {
  if (value == null) return '—';
  final d = value.toLocal();
  return '${d.day} ${_monthsAr[d.month - 1]} ${d.year}';
}

/// تاريخ ووقت محلّيّان: «5 مارس 2026، 14:05».
String fmtDateTime(DateTime? value) {
  if (value == null) return '—';
  final d = value.toLocal();
  final hh = d.hour.toString().padLeft(2, '0');
  final mm = d.minute.toString().padLeft(2, '0');
  return '${fmtDate(d)}، $hh:$mm';
}

/// يحلّل تاريخ ISO من الخادم ثمّ ينسّقه؛ نصّ غير صالح ⇒ يُعاد كما هو (لا اختلاق).
String fmtIsoDate(String? iso) {
  if (iso == null || iso.isEmpty) return '—';
  final d = DateTime.tryParse(iso);
  return d == null ? iso : fmtDate(d);
}

/// «منذ ...» لعمر البيانات (لافتة «آخر تحديث»).
String fmtAge(DateTime? at, {DateTime? now}) {
  if (at == null) return '—';
  final diff = (now ?? DateTime.now()).difference(at);
  if (diff.inMinutes < 1) return 'الآن';
  if (diff.inMinutes < 60) return 'منذ ${diff.inMinutes} دقيقة';
  if (diff.inHours < 24) return 'منذ ${diff.inHours} ساعة';
  return 'منذ ${diff.inDays} يوم';
}
