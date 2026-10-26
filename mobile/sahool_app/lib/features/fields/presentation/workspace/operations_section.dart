// SAHOOL — features/fields/presentation/workspace/operations_section.dart
// تبويب «العمليّات»: ثلاثة أجزاء بمبدّل واحد — الأنشطة (سجلّ + زرّ تسجيل)،
// الريّ (توصية FAO-56 + جداول الحقل + رابط الريّ التشغيليّ)، والسجلّ الزمنيّ
// الموحّد (بالتوقيت المحلّيّ لا UTC). روابط المهامّ والريّ بمسارات ميزاتها.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

import '../common/cross_feature_routes.dart';
import '../common/field_labels.dart';
import '../common/load_cubit.dart';
import 'activity_form_sheet.dart';
import 'overview_section.dart' show kUrgencyAr;
import 'workspace_deps.dart';
import 'workspace_widgets.dart';

enum OpsPart { activities, irrigation, timeline }

const Map<String, String> kTimelineCategoryAr = {
  'lifecycle': 'دورة الحياة',
  'operation': 'عمليّة',
  'observation': 'مشاهدة',
  'calibration': 'معايرة',
  'weather': 'طقس',
  'system': 'نظام',
};

class WOperationsSection extends StatefulWidget {
  const WOperationsSection({
    super.key,
    required this.fieldId,
    required this.field,
    this.role,
  });

  final String fieldId;
  final Map<String, dynamic> field;
  final AppRole? role;

  @override
  State<WOperationsSection> createState() => _WOperationsSectionState();
}

class _WOperationsSectionState extends State<WOperationsSection> {
  late final WorkspaceDeps _deps = context.read<WorkspaceDeps>();
  OpsPart _part = OpsPart.activities;

  // تُنشأ عند أوّل فتح لكلّ جزء (لا جلب لما لم يُعرض).
  LoadCubit<List<Map<String, dynamic>>>? _activities;
  LoadCubit<List<Map<String, dynamic>>>? _schedules;
  LoadCubit<Map<String, dynamic>>? _advice;
  LoadCubit<Map<String, dynamic>>? _timeline;

  AppRole get _role => widget.role ?? normalizeRole(currentRole());

  LoadCubit<List<Map<String, dynamic>>> get activities =>
      _activities ??= LoadCubit(
        () => _deps.fields.fetchFieldActivities(widget.fieldId),
      )..load();
  LoadCubit<List<Map<String, dynamic>>> get schedules =>
      _schedules ??= LoadCubit(
        () => _deps.irrigation.listSchedules(fieldId: widget.fieldId),
      )..load();
  LoadCubit<Map<String, dynamic>> get advice => _advice ??= LoadCubit(
    () => _deps.fields.fetchIrrigationAdvice(widget.fieldId),
  )..load();
  LoadCubit<Map<String, dynamic>> get timeline => _timeline ??= LoadCubit(
    () => _deps.fields.fetchUnifiedTimeline(widget.fieldId),
  )..load();

  @override
  void dispose() {
    _activities?.close();
    _schedules?.close();
    _advice?.close();
    _timeline?.close();
    super.dispose();
  }

  Future<void> _refresh() async {
    switch (_part) {
      case OpsPart.activities:
        await activities.refresh();
      case OpsPart.irrigation:
        await Future.wait([schedules.refresh(), advice.refresh()]);
      case OpsPart.timeline:
        await timeline.refresh();
    }
  }

  Future<void> _logActivity() async {
    final messenger = ScaffoldMessenger.of(context);
    final saved = await showActivityFormSheet(
      context,
      fieldId: widget.fieldId,
      api: _deps.fields,
    );
    if (!saved) return;
    messenger.showSnackBar(
      const SnackBar(content: Text('سُجّل النشاط في سجلّ الحقل')),
    );
    await activities.refresh();
    if (_timeline != null) await _timeline!.refresh();
  }

  @override
  Widget build(BuildContext context) => RefreshIndicator(
    onRefresh: _refresh,
    child: ListView(
      padding: const EdgeInsets.all(SahoolSpacing.page),
      children: [
        SegmentedButton<OpsPart>(
          key: const ValueKey('ops_parts'),
          showSelectedIcon: false,
          segments: const [
            ButtonSegment(
              value: OpsPart.activities,
              label: Text('الأنشطة'),
              icon: Icon(Icons.assignment_outlined),
            ),
            ButtonSegment(
              value: OpsPart.irrigation,
              label: Text('الريّ'),
              icon: Icon(Icons.water_drop_outlined),
            ),
            ButtonSegment(
              value: OpsPart.timeline,
              label: Text('السجلّ'),
              icon: Icon(Icons.timeline_rounded),
            ),
          ],
          selected: {_part},
          onSelectionChanged: (s) => setState(() => _part = s.first),
        ),
        const SizedBox(height: SahoolSpacing.md),
        ...switch (_part) {
          OpsPart.activities => _activitiesPart(context),
          OpsPart.irrigation => _irrigationPart(context),
          OpsPart.timeline => _timelinePart(context),
        },
      ],
    ),
  );

  List<Widget> _activitiesPart(BuildContext context) => [
    if (canMutate(_role.name))
      Padding(
        padding: const EdgeInsets.only(bottom: SahoolSpacing.md),
        child: PrimaryButton(
          key: const ValueKey('ops_log_activity'),
          icon: Icons.add_task_rounded,
          label: 'تسجيل نشاط',
          onPressed: _logActivity,
        ),
      ),
    WSectionCard(
      title: 'أنشطة الحقل',
      icon: Icons.assignment_outlined,
      child: InlineLoadView<List<Map<String, dynamic>>>(
        cubit: activities,
        builder: (context, list) => list.isEmpty
            ? Text('لا أنشطة مسجّلة بعد.', style: context.textStyles.bodyMedium)
            : Column(
                children: [
                  for (final a in list)
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text(
                        wText(
                          a['title_ar'],
                          kActivityTypeAr[a['activity_type']] ?? 'نشاط',
                        ),
                      ),
                      subtitle: Text(
                        [
                          kActivityTypeAr[a['activity_type']] ??
                              wText(a['activity_type'], ''),
                          fmtDay(a['performed_on'] ?? a['scheduled_for']),
                        ].where((s) => s.isNotEmpty).join(' · '),
                      ),
                      trailing: wText(a['status'], '').isEmpty
                          ? null
                          : StatusChip(
                              label:
                                  kActivityStatusAr[a['status']] ??
                                  wText(a['status']),
                              tone: a['status'] == 'planned'
                                  ? StatusTone.info
                                  : StatusTone.success,
                            ),
                    ),
                ],
              ),
      ),
    ),
    SecondaryButton(
      icon: Icons.checklist_rounded,
      label: 'مهامّ هذا الحقل',
      onPressed: () => openFeatureRoute<void>(
        context,
        CrossFeatureRoutes.tasks,
        query: {'field_id': widget.fieldId},
      ),
    ),
  ];

  List<Widget> _irrigationPart(BuildContext context) => [
    WSectionCard(
      title: 'معلومات الريّ',
      icon: Icons.water_outlined,
      child: Column(
        children: [
          WInfoRow(
            'نوع الريّ',
            wText(
              widget.field['irrigation_type_ar'] ??
                  widget.field['irrigation_type'],
              kNotMeasured,
            ),
          ),
          WInfoRow(
            'مصدر المياه',
            wText(
              widget.field['water_source_ar'] ?? widget.field['water_source'],
              kNotMeasured,
            ),
          ),
        ],
      ),
    ),
    WSectionCard(
      title: 'توصية الريّ (FAO-56)',
      icon: Icons.water_drop_outlined,
      child: InlineLoadView<Map<String, dynamic>>(
        cubit: advice,
        builder: (context, d) {
          final urgency = wText(d['urgency'], '');
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (urgency.isNotEmpty)
                Align(
                  alignment: AlignmentDirectional.centerStart,
                  child: StatusChip(
                    label: kUrgencyAr[urgency] ?? urgency,
                    tone: switch (urgency) {
                      'high' => StatusTone.danger,
                      'moderate' => StatusTone.warning,
                      'low' => StatusTone.info,
                      _ => StatusTone.neutral,
                    },
                  ),
                ),
              WInfoRow('الكمّيّة الموصى بها', fmtMm(wNum(d['recommended_mm']))),
              WInfoRow('التوقيت', wText(d['timing_ar'])),
              if (wText(d['rationale_ar'], '').isNotEmpty)
                Text(
                  wText(d['rationale_ar']),
                  style: context.textStyles.bodySmall,
                ),
            ],
          );
        },
      ),
    ),
    WSectionCard(
      title: 'جداول الريّ',
      icon: Icons.schedule_rounded,
      child: InlineLoadView<List<Map<String, dynamic>>>(
        cubit: schedules,
        builder: (context, list) => list.isEmpty
            ? Text(
                'لا جداول ريّ مرتبطة بهذا الحقل.',
                style: context.textStyles.bodyMedium,
              )
            : Column(
                children: [
                  for (final s in list)
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: Icon(
                        s['enabled'] == true
                            ? Icons.schedule_rounded
                            : Icons.pause_circle_outline_rounded,
                      ),
                      title: Text(wText(s['name'], 'جدول')),
                      subtitle: Text(
                        [
                          wText(s['start_time'], ''),
                          if (wNum(s['duration_min']) != null)
                            '${fmtNumber(wNum(s['duration_min']), decimals: 0)} دقيقة',
                          s['enabled'] == true ? 'مفعّل' : 'متوقّف',
                        ].where((x) => x.isNotEmpty).join(' · '),
                      ),
                    ),
                ],
              ),
      ),
    ),
    SecondaryButton(
      icon: Icons.tune_rounded,
      label: 'الريّ التشغيليّ (الصمّامات والجداول)',
      onPressed: () => openFeatureRoute<void>(
        context,
        CrossFeatureRoutes.irrigation,
        query: {'field_id': widget.fieldId},
      ),
    ),
  ];

  List<Widget> _timelinePart(BuildContext context) => [
    WSectionCard(
      title: 'السجلّ الزمنيّ للحقل',
      icon: Icons.timeline_rounded,
      child: InlineLoadView<Map<String, dynamic>>(
        cubit: timeline,
        builder: (context, data) {
          final events = wList(data['events']);
          final note = wText(data['note_ar'] ?? data['error'], '');
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (note.isNotEmpty)
                Text(note, style: context.textStyles.bodySmall),
              if (events.isEmpty)
                Text('لا أحداث بعد.', style: context.textStyles.bodyMedium),
              for (final e in events)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(
                    wText(e['summary_ar'], wText(e['event_type'], 'حدث')),
                  ),
                  subtitle: Text(
                    fmtDateTime(parseDate(e['timestamp'])),
                    key: ValueKey('event_time_${events.indexOf(e)}'),
                  ),
                  trailing: wText(e['category'], '').isEmpty
                      ? null
                      : StatusChip(
                          label:
                              kTimelineCategoryAr[e['category']] ??
                              wText(e['category']),
                          tone: StatusTone.info,
                        ),
                ),
            ],
          );
        },
      ),
    ),
  ];
}
