// SAHOOL — features/activities/presentation/activity_labels.dart
// تسميات الأنشطة والخطّ الزمنيّ (تطابق الويب ActivitiesPage TYPE_LABELS).
import 'package:flutter/material.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/status_chip.dart';
import 'package:sahool_app/features/activities/data/field_activity.dart';

const Map<String, String> kActivityTypeAr = {
  'planting': 'بذر/زراعة',
  'fertilization': 'تسميد',
  'irrigation': 'ريّ',
  'spraying': 'رشّ',
  'pruning': 'تقليم',
  'harvest': 'حصاد',
  'scouting': 'كشف/مسح',
};

const Map<String, IconData> _activityIcons = {
  'planting': Icons.spa_outlined,
  'fertilization': Icons.grass_outlined,
  'irrigation': Icons.water_drop_outlined,
  'spraying': Icons.sanitizer_outlined,
  'pruning': Icons.content_cut_outlined,
  'harvest': Icons.agriculture_outlined,
  'scouting': Icons.travel_explore_outlined,
};

String activityTypeAr(String t) =>
    t.isEmpty ? 'نوع غير محدّد' : (kActivityTypeAr[t] ?? t);

IconData activityTypeIcon(String t) =>
    _activityIcons[t] ?? Icons.event_note_outlined;

String activityStatusAr(String s) => switch (s) {
  'done' => 'مُنفَّذ',
  'planned' => 'مُجدوَل',
  'skipped' => 'مُتجاوَز',
  _ => s.isEmpty ? '—' : s,
};

StatusTone activityStatusTone(String s) => switch (s) {
  'done' => StatusTone.success,
  'planned' => StatusTone.warning,
  _ => StatusTone.neutral,
};

/// سطر التاريخ: التنفيذ أو الجدولة (تواريخ تقويميّة محلّيّة).
String activityDateLine(FieldActivity a) {
  if (a.performedOn != null) return 'نُفِّذ: ${fmtIsoDate(a.performedOn)}';
  if (a.scheduledFor != null) return 'مُجدوَل: ${fmtIsoDate(a.scheduledFor)}';
  return 'سُجِّل: ${fmtDate(a.createdAt)}';
}

/// فئات الخطّ الزمنيّ (TimelineCategory في api/field_timeline.py).
const Map<String, String> kTimelineCategoryAr = {
  'operation': 'عمليّات',
  'observation': 'مشاهدات',
  'lifecycle': 'مراحل',
  'weather': 'طقس',
  'calibration': 'معايرة',
  'system': 'النظام',
};

const Map<String, IconData> _categoryIcons = {
  'operation': Icons.agriculture_outlined,
  'observation': Icons.visibility_outlined,
  'lifecycle': Icons.timeline_outlined,
  'weather': Icons.cloud_outlined,
  'calibration': Icons.tune_outlined,
  'system': Icons.settings_outlined,
};

String timelineCategoryAr(String c) => kTimelineCategoryAr[c] ?? c;
IconData timelineCategoryIcon(String c) =>
    _categoryIcons[c] ?? Icons.circle_outlined;

/// وقت الحدث محلّيّاً؛ طابع غير صالح يُعرَض كما هو (لا اختلاق).
String timelineTimeLabel(TimelineEvent e) => e.at == null
    ? (e.rawTimestamp.isEmpty ? '—' : e.rawTimestamp)
    : fmtDateTime(e.at);
