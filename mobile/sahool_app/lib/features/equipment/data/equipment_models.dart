// SAHOOL — features/equipment/data/equipment_models.dart
// نماذج المعدّات والصيانة كما يُعيدها الخادم (services/sahool-platform/api/
// routers/equipment.py) وقيود قاعدة البيانات (migrations/v23_equipment.sql):
//   status ∈ operational | maintenance | broken | retired
//   kind ∈ scheduled | repair | breakdown | inspection
//   maintenance.status ∈ planned | done | cancelled
// كانت الشاشة القديمة تفحص 'active' — قيمة لا يُنتجها الخادم — فتُرسَم كلّ معدّة
// عاملة بلون «غير معروف».

const Map<String, String> kEquipmentTypes = {
  'tractor': 'جرّار',
  'pump': 'مضخّة',
  'harvester': 'حصّادة',
  'sprayer': 'رشّاشة',
  'other': 'أخرى',
};

const Map<String, String> kEquipmentStatuses = {
  'operational': 'تعمل',
  'maintenance': 'في الصيانة',
  'broken': 'معطّلة',
  'retired': 'خارج الخدمة',
};

const Map<String, String> kMaintenanceKinds = {
  'scheduled': 'صيانة دوريّة',
  'repair': 'إصلاح',
  'breakdown': 'عطل',
  'inspection': 'فحص',
};

const Map<String, String> kMaintenanceStatuses = {
  'planned': 'مخطّطة',
  'done': 'مُنجَزة',
  'cancelled': 'ملغاة',
};

double? _toDouble(Object? v) {
  if (v is num) return v.toDouble();
  if (v is String) return double.tryParse(v);
  return null;
}

DateTime? _calendarDate(Object? v) {
  if (v is! String || v.isEmpty) return null;
  final d = DateTime.tryParse(v);
  return d == null ? null : DateTime(d.year, d.month, d.day);
}

/// `yyyy-MM-dd` لتاريخ تقويميّ (لا إزاحة منطقة زمنيّة).
String equipmentIsoDate(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-'
    '${d.month.toString().padLeft(2, '0')}-'
    '${d.day.toString().padLeft(2, '0')}';

class Equipment {
  const Equipment({
    required this.id,
    required this.name,
    required this.type,
    required this.status,
    required this.operatingHours,
    required this.purchaseDate,
  });

  factory Equipment.fromJson(Map<String, dynamic> m) {
    final id = m['equipment_id'];
    if (id == null) {
      throw const FormatException('معدّة بلا equipment_id في استجابة الخادم.');
    }
    return Equipment(
      id: id.toString(),
      name: (m['name'] ?? '').toString(),
      type: (m['type'] ?? 'other').toString(),
      status: (m['status'] ?? '').toString(),
      operatingHours: _toDouble(m['operating_hours']),
      purchaseDate: _calendarDate(m['purchase_date']),
    );
  }

  final String id;
  final String name;
  final String type;
  final String status;
  final double? operatingHours;
  final DateTime? purchaseDate;

  String get typeLabel => kEquipmentTypes[type] ?? type;
  String get statusLabel =>
      kEquipmentStatuses[status] ?? (status.isEmpty ? 'غير معروفة' : status);
}

class MaintenanceRecord {
  const MaintenanceRecord({
    required this.id,
    required this.kind,
    required this.status,
    required this.scheduledDate,
    required this.performedDate,
    required this.costUsd,
    required this.notes,
  });

  factory MaintenanceRecord.fromJson(Map<String, dynamic> m) =>
      MaintenanceRecord(
        id: (m['maintenance_id'] ?? '').toString(),
        kind: (m['kind'] ?? '').toString(),
        status: (m['status'] ?? '').toString(),
        scheduledDate: _calendarDate(m['scheduled_date']),
        performedDate: _calendarDate(m['performed_date']),
        costUsd: _toDouble(m['cost_usd']),
        notes: m['notes']?.toString(),
      );

  final String id;
  final String kind;
  final String status;
  final DateTime? scheduledDate;
  final DateTime? performedDate;

  /// الخادم يخزّن التكلفة بالدولار الأمريكيّ (cost_usd).
  final double? costUsd;
  final String? notes;

  String get kindLabel => kMaintenanceKinds[kind] ?? kind;
  String get statusLabel => kMaintenanceStatuses[status] ?? status;

  bool get isPlanned => status == 'planned';

  /// مخطّطة وتاريخها قبل اليوم.
  bool isOverdue(DateTime now) {
    final d = scheduledDate;
    if (!isPlanned || d == null) return false;
    return d.isBefore(DateTime(now.year, now.month, now.day));
  }
}
