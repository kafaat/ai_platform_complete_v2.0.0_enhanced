// SAHOOL — features/tasks/presentation/task_labels.dart
// تسميات المهام العربيّة ونغماتها. النوع المجهول يُعرَض كما أرسله الخادم، والغائب
// «نوع غير محدّد» — لا «كشف ميدانيّ» افتراضيّ.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/status_chip.dart';
import 'package:sahool_app/features/tasks/data/field_task.dart';

/// أنواع المهام التي تنتجها المنصّة (weather.py `_task_type_for_operation` +
/// أنواع التوصيات) مع أسمائها في الويب (TasksPage TASK_CONFIG).
const Map<String, String> kTaskTypeAr = {
  'irrigation': 'ريّ',
  'fertilization': 'تسميد',
  'spraying': 'رشّ',
  'harvest': 'حصاد',
  'sowing': 'بذر',
  'planting': 'زراعة',
  'scouting': 'كشف ميدانيّ',
  'soil_sampling': 'أخذ عيّنة تربة',
  'pruning': 'تقليم',
};

const Map<String, IconData> _typeIcons = {
  'irrigation': Icons.water_drop_outlined,
  'fertilization': Icons.grass_outlined,
  'spraying': Icons.sanitizer_outlined,
  'harvest': Icons.agriculture_outlined,
  'sowing': Icons.spa_outlined,
  'planting': Icons.spa_outlined,
  'scouting': Icons.travel_explore_outlined,
  'soil_sampling': Icons.science_outlined,
  'pruning': Icons.content_cut_outlined,
};

String taskTypeAr(String type) =>
    type.isEmpty ? 'نوع غير محدّد' : (kTaskTypeAr[type] ?? type);

IconData taskTypeIcon(String type) =>
    _typeIcons[type] ?? Icons.assignment_outlined;

const Map<String, String> kTaskStatusAr = {
  TaskStatus.pending: 'بانتظار التنفيذ',
  TaskStatus.inProgress: 'قيد التنفيذ',
  TaskStatus.completed: 'مُنجزة',
  TaskStatus.cancelled: 'ملغاة',
};

String taskStatusAr(String s) => kTaskStatusAr[s] ?? s;

StatusTone taskStatusTone(String s) => switch (s) {
  TaskStatus.completed => StatusTone.success,
  TaskStatus.inProgress => StatusTone.info,
  TaskStatus.pending => StatusTone.warning,
  _ => StatusTone.neutral,
};

/// الأولويّة تصاعديّة على الخادم: 1 الأعلى … 5 روتينيّ (weather.py:1269).
const Map<int, String> kPriorityAr = {
  1: 'حرجة',
  2: 'عالية',
  3: 'متوسّطة',
  4: 'منخفضة',
  5: 'روتينيّة',
};

String? priorityAr(int? p) => p == null ? null : kPriorityAr[p];

/// المدّة التقديريّة بالدقائق؛ الغائبة «غير مقيس».
String fmtDurationMin(int? minutes) {
  if (minutes == null) return kNotMeasured;
  if (minutes < 60) return '$minutes دقيقة';
  final h = minutes ~/ 60;
  final m = minutes % 60;
  return m == 0 ? '$h ساعة' : '$h ساعة و$m دقيقة';
}

/// الكلفة التقديريّة كما يخزّنها الخادم (estimated_cost_usd — بالدولار). لا
/// تحويل إلى الريال: لا سعر صرف من الخادم، والتحويل تخمين.
String fmtCostUsd(double? usd) =>
    usd == null ? kNotMeasured : '${fmtNumber(usd, decimals: 2)} دولار أمريكي';
