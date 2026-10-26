// SAHOOL — features/fields/data/field_list_query.dart
// منطق بحث/تصفية/ترتيب قائمة الحقول — دوالّ نقيّة تُختبر بلا واجهة.
// صدق الترتيب: «الأولويّة» من تنبيهات ومهامّ مخزّنة فعلاً (priority-queue)،
// و«الحالة» من quality_grade الذي يرسله الخادم؛ لا صحّة NDVI مخترعة في القائمة
// (GET /api/v1/fields لا يرسل NDVI). الحقل غير المقيس يأتي آخراً لا بصفر.
import 'package:sahool_app/core/utils/formatters.dart';

enum FieldSort {
  priority('الأولويّة (تنبيهات ومهامّ)'),
  status('الحالة (الأحوج أوّلاً)'),
  name('الاسم'),
  area('المساحة (الأكبر أوّلاً)');

  const FieldSort(this.labelAr);
  final String labelAr;
}

/// أولويّة حقل مجمّعة من عناصر priority-queue.
class FieldPriority {
  const FieldPriority({required this.count, required this.worstRank});
  const FieldPriority.none() : count = 0, worstRank = 9;

  /// عدد التنبيهات والمهامّ المفتوحة.
  final int count;

  /// أشدّ خطورة: 0 حرج · 1 مرتفع · 2 متوسّط · 3 منخفض · 9 لا شيء.
  final int worstRank;

  static const _rank = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3};
  static const severities = ['critical', 'high', 'medium', 'low'];

  String? get worstSeverity =>
      worstRank < severities.length ? severities[worstRank] : null;

  FieldPriority add(String? severity) => FieldPriority(
    count: count + 1,
    worstRank: (_rank[severity] ?? 2) < worstRank
        ? (_rank[severity] ?? 2)
        : worstRank,
  );
}

/// أولويّات مُقاسة لمجموعة حقول: [byField] للمُقاسة فقط.
class PriorityData {
  const PriorityData({required this.byField, this.partial = false});

  final Map<String, FieldPriority> byField;

  /// true حين تعذّر بعض المصادر (degraded أو فشل مزرعة) ⇒ يُقال في الواجهة.
  final bool partial;

  /// يجمّع عناصر طوابير متعدّدة. [measured] الحقول التي غطّتها الطوابير
  /// الناجحة (حتّى بلا عناصر ⇒ أولويّة «لا شيء» مقيسة).
  factory PriorityData.fromItems(
    Iterable<Map<String, dynamic>> items, {
    required Iterable<String> measured,
    bool partial = false,
  }) {
    final out = <String, FieldPriority>{
      for (final id in measured) id: const FieldPriority.none(),
    };
    for (final it in items) {
      final id = '${it['field_id'] ?? ''}';
      if (id.isEmpty || !out.containsKey(id)) continue;
      out[id] = out[id]!.add(it['severity'] as String?);
    }
    return PriorityData(byField: out, partial: partial);
  }
}

class FieldQuery {
  const FieldQuery({
    this.text = '',
    this.farmId,
    this.crop,
    this.status,
    this.sort = FieldSort.name,
  });

  final String text;

  /// '' = حقول بلا مزرعة؛ null = كلّ المزارع.
  final String? farmId;

  /// '' = بلا محصول؛ null = كلّ المحاصيل.
  final String? crop;
  final String? status;
  final FieldSort sort;

  bool get hasFilters =>
      text.trim().isNotEmpty ||
      farmId != null ||
      crop != null ||
      status != null;

  FieldQuery copyWith({
    String? text,
    String? Function()? farmId,
    String? Function()? crop,
    String? Function()? status,
    FieldSort? sort,
  }) => FieldQuery(
    text: text ?? this.text,
    farmId: farmId == null ? this.farmId : farmId(),
    crop: crop == null ? this.crop : crop(),
    status: status == null ? this.status : status(),
    sort: sort ?? this.sort,
  );
}

String _s(Object? v) => v == null ? '' : '$v'.trim();

String fieldListName(Map<String, dynamic> f) =>
    _s(f['name_ar'] ?? f['field_name'] ?? f['name']);

String fieldListCrop(Map<String, dynamic> f) {
  final c = _s(f['crop']);
  return c == '—' ? '' : c;
}

double? fieldListArea(Map<String, dynamic> f) {
  final a = f['area_ha'];
  return (a is num && a > 0) ? a.toDouble() : null;
}

String _norm(String s) => normalizeDigits(s).toLowerCase();

/// يطبّق البحث والتصفية والترتيب ويُعيد قائمة جديدة.
List<Map<String, dynamic>> applyFieldQuery(
  List<Map<String, dynamic>> fields,
  FieldQuery q, {
  PriorityData? priority,
}) {
  final needle = _norm(q.text.trim());
  final out = fields.where((f) {
    if (q.farmId != null && _s(f['farm_id']) != q.farmId) return false;
    if (q.crop != null && fieldListCrop(f) != q.crop) return false;
    if (q.status != null && _s(f['quality_grade']) != q.status) return false;
    if (needle.isEmpty) return true;
    final hay = [
      fieldListName(f),
      fieldListCrop(f),
      _s(f['field_code']),
      _s(f['region']),
    ].map(_norm).join(' ');
    return hay.contains(needle);
  }).toList();

  int byName(Map<String, dynamic> a, Map<String, dynamic> b) =>
      fieldListName(a).compareTo(fieldListName(b));

  const grade = {'BLOCKED': 0, 'PENDING_LAB': 1, 'LIMITED': 2, 'READY': 3};
  switch (q.sort) {
    case FieldSort.name:
      out.sort(byName);
    case FieldSort.area:
      out.sort((a, b) {
        final x = fieldListArea(a), y = fieldListArea(b);
        if (x == null && y == null) return byName(a, b);
        if (x == null) return 1;
        if (y == null) return -1;
        final c = y.compareTo(x);
        return c != 0 ? c : byName(a, b);
      });
    case FieldSort.status:
      out.sort((a, b) {
        final c = (grade[_s(a['quality_grade'])] ?? 4).compareTo(
          grade[_s(b['quality_grade'])] ?? 4,
        );
        return c != 0 ? c : byName(a, b);
      });
    case FieldSort.priority:
      final byField = priority?.byField ?? const {};
      out.sort((a, b) {
        final pa = byField[_s(a['field_id'])];
        final pb = byField[_s(b['field_id'])];
        if (pa == null && pb == null) return byName(a, b);
        if (pa == null) return 1; // غير المقيس آخراً
        if (pb == null) return -1;
        var c = pa.worstRank.compareTo(pb.worstRank);
        if (c != 0) return c;
        c = pb.count.compareTo(pa.count);
        return c != 0 ? c : byName(a, b);
      });
  }
  return out;
}
