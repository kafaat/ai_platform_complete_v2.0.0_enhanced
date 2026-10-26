// SAHOOL — features/inventory/data/inventory_models.dart
// نماذج المخزون كما يُعيدها الخادم حرفيّاً (services/sahool-platform/api/routers/
// inventory.py): GET /inventory/items و GET /inventory/expiring. لا حقل يُخمَّن:
// ما لا يُعيده الخادم (حركة صرف، ربط بحقل، بيانات سلامة المبيد) لا يُمثَّل هنا.

/// الفئات كما يقبلها الخادم: ^(fertilizer|pesticide|seed|spare_part|other)$
const Map<String, String> kInventoryCategories = {
  'fertilizer': 'سماد',
  'pesticide': 'مبيد',
  'seed': 'بذور',
  'spare_part': 'قطع غيار',
  'other': 'أخرى',
};

String inventoryCategoryLabel(String category) =>
    kInventoryCategories[category] ?? category;

/// مواد زراعيّة كيميائيّة تستحقّ تنبيه سلامة.
bool isAgrochemical(String category) => category == 'pesticide';

double? _toDouble(Object? v) {
  if (v is num) return v.toDouble();
  if (v is String) return double.tryParse(v);
  return null;
}

/// يحلّل تاريخاً بلا وقت (`2026-03-05`) كتاريخ تقويميّ محلّيّ.
DateTime? parseCalendarDate(Object? v) {
  if (v is! String || v.isEmpty) return null;
  final d = DateTime.tryParse(v);
  if (d == null) return null;
  return DateTime(d.year, d.month, d.day);
}

/// `yyyy-MM-dd` لإرسال تاريخ تقويميّ (لا منطقة زمنيّة تُزيحه يوماً).
String isoCalendarDate(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-'
    '${d.month.toString().padLeft(2, '0')}-'
    '${d.day.toString().padLeft(2, '0')}';

class InventoryItem {
  const InventoryItem({
    required this.id,
    required this.category,
    required this.name,
    required this.unit,
    required this.reorderLevel,
    required this.totalQuantity,
    required this.lowStock,
  });

  factory InventoryItem.fromJson(Map<String, dynamic> m) {
    final id = m['item_id'];
    if (id == null) {
      throw const FormatException('عنصر مخزون بلا item_id في استجابة الخادم.');
    }
    return InventoryItem(
      id: id.toString(),
      category: (m['category'] ?? 'other').toString(),
      name: (m['name'] ?? '').toString(),
      unit: (m['unit'] ?? '').toString(),
      reorderLevel: _toDouble(m['reorder_level']),
      totalQuantity: _toDouble(m['total_quantity']),
      lowStock: m['low_stock'] == true,
    );
  }

  final String id;
  final String category;
  final String name;
  final String unit;

  /// null ⇒ لم يُحدَّد حدّ إعادة طلب (لا يُحسب «منخفض»).
  final double? reorderLevel;

  /// مجموع الدفعات كما حسبه الخادم؛ null ⇒ لم يُعِده الخادم.
  final double? totalQuantity;

  /// يحسبه الخادم: الكمّيّة ≤ حدّ إعادة الطلب.
  final bool lowStock;

  String get categoryLabel => inventoryCategoryLabel(category);
}

class ExpiringBatch {
  const ExpiringBatch({
    required this.batchId,
    required this.itemId,
    required this.name,
    required this.quantity,
    required this.unit,
    required this.expiryDate,
  });

  factory ExpiringBatch.fromJson(Map<String, dynamic> m) => ExpiringBatch(
    batchId: (m['batch_id'] ?? '').toString(),
    itemId: (m['item_id'] ?? '').toString(),
    name: (m['name'] ?? '').toString(),
    quantity: _toDouble(m['quantity']),
    unit: m['unit']?.toString(),
    expiryDate: parseCalendarDate(m['expiry_date']),
  );

  final String batchId;
  final String itemId;
  final String name;
  final double? quantity;
  final String? unit;
  final DateTime? expiryDate;

  /// أيّام حتّى الانتهاء (سالب ⇒ منتهية). null ⇒ لا تاريخ.
  int? daysLeft(DateTime now) {
    final e = expiryDate;
    if (e == null) return null;
    // UTC يتجنّب يوماً ناقصاً عند تبدّل التوقيت الصيفيّ.
    final today = DateTime.utc(now.year, now.month, now.day);
    return DateTime.utc(e.year, e.month, e.day).difference(today).inDays;
  }

  bool isExpired(DateTime now) => (daysLeft(now) ?? 1) < 0;
}
