// SAHOOL — features/fields/presentation/fields_screen.dart
// «حقولي» (تبويب الحقول): بحث، تصفية بالمزرعة/المحصول/الحالة، ترتيب بالأولويّة
// أو الحالة أو الاسم أو المساحة، وحالة فارغة تدعو لإضافة حقل. الخريطة ملك ميزة
// الخرائط: زرّ «الخريطة» يفتح مسارها إن سُجِّل. صدق: القائمة من GET /api/v1/fields
// فقط؛ المساحة الغائبة «غير مقيس» والأولويّة غير المقيسة لا تُعرَض كصفر.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/farms/data/farms_api.dart';
import 'package:sahool_app/features/fields/data/field_list_query.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';

import '../fields_routes.dart';
import 'common/cross_feature_routes.dart';
import 'common/field_labels.dart';
import 'common/load_cubit.dart';
import 'fields_list_cubit.dart';

class FieldsScreen extends StatelessWidget {
  const FieldsScreen({super.key, this.fieldsApi, this.farmsApi, this.role});

  final FieldsApi? fieldsApi;
  final FarmsApi? farmsApi;

  /// الدور (للاختبار)؛ افتراضيّاً من الجلسة.
  final AppRole Function()? role;

  @override
  Widget build(BuildContext context) => BlocProvider(
    create: (_) => FieldsListCubit(
      fieldsApi ?? FieldsApi.instance,
      farmsApi ?? FarmsApi.instance,
    )..load(),
    child: _FieldsView(role: (role ?? () => normalizeRole(currentRole()))()),
  );
}

class _FieldsView extends StatefulWidget {
  const _FieldsView({required this.role});
  final AppRole role;

  @override
  State<_FieldsView> createState() => _FieldsViewState();
}

class _FieldsViewState extends State<_FieldsView> {
  final _search = TextEditingController();

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  bool get _canCreate => canMutate(widget.role.name);

  Future<void> _openCreate() async {
    final cubit = context.read<FieldsListCubit>();
    await Navigator.of(context).pushNamed<Object?>(FieldsRoutes.create);
    if (!mounted) return;
    // المعالج قد يُنشئ حقلاً ثمّ يُغلق بلا نتيجة ⇒ نُحدّث دائماً بصمت.
    await cubit.load(silent: true);
  }

  void _openWorkspace(Map<String, dynamic> field) => Navigator.of(
    context,
  ).pushNamed<void>(FieldsRoutes.workspace, arguments: field);

  @override
  Widget build(BuildContext context) {
    final state = context.watch<FieldsListCubit>().state;
    final loaded = state.fields is LoadLoaded;
    return Scaffold(
      appBar: AppBar(
        title: const Text('حقولي'),
        actions: [
          AppIconButton(
            key: const ValueKey('fields_map_toggle'),
            icon: Icons.map_outlined,
            tooltip: 'عرض الحقول على الخريطة',
            onPressed: () =>
                openFeatureRoute<void>(context, CrossFeatureRoutes.maps),
          ),
          AppIconButton(
            icon: Icons.refresh_rounded,
            tooltip: 'تحديث',
            onPressed: () => context.read<FieldsListCubit>().load(),
          ),
        ],
      ),
      floatingActionButton: (_canCreate && loaded && state.all.isNotEmpty)
          ? AppFab(
              heroKey: 'fields',
              label: 'إضافة حقل',
              icon: Icons.add_location_alt_outlined,
              onPressed: _openCreate,
            )
          : null,
      body: switch (state.fields) {
        LoadLoading() => const LoadingState(message: 'جارٍ تحميل الحقول'),
        LoadFailed(:final error) => ErrorState(
          error: error,
          title: 'تعذّر تحميل الحقول',
          onRetry: () => context.read<FieldsListCubit>().load(),
        ),
        LoadLoaded(:final data) when data.isEmpty => RefreshIndicator(
          onRefresh: () => context.read<FieldsListCubit>().load(silent: true),
          child: ListView(
            children: [
              EmptyState(
                key: const ValueKey('fields_empty'),
                icon: Icons.terrain_outlined,
                title: 'لا حقول بعد',
                message: _canCreate
                    ? 'أضف حقلك الأوّل برسم حدوده على الخريطة أو المشي حوله.'
                    : 'لم يُضَف أيّ حقل لحسابك بعد.',
                actionLabel: _canCreate ? 'إضافة حقل' : null,
                onAction: _canCreate ? _openCreate : null,
              ),
            ],
          ),
        ),
        LoadLoaded() => _list(context, state),
      },
    );
  }

  Widget _list(BuildContext context, FieldsListState state) {
    final cubit = context.read<FieldsListCubit>();
    final visible = state.visible;
    final priorityState = state.priority;
    final byField = switch (priorityState) {
      LoadLoaded(:final data) => data.byField,
      _ => const <String, FieldPriority>{},
    };
    final showPriority = state.query.sort == FieldSort.priority;
    return RefreshIndicator(
      onRefresh: () => cubit.load(silent: true),
      child: ListView(
        padding: const EdgeInsetsDirectional.fromSTEB(
          SahoolSpacing.page,
          SahoolSpacing.md,
          SahoolSpacing.page,
          96,
        ),
        children: [
          TextField(
            key: const ValueKey('fields_search'),
            controller: _search,
            onChanged: cubit.setText,
            textInputAction: TextInputAction.search,
            decoration: InputDecoration(
              prefixIcon: const Icon(Icons.search_rounded),
              hintText: 'ابحث بالاسم أو المحصول أو الرمز',
              suffixIcon: _search.text.isEmpty
                  ? null
                  : AppIconButton(
                      icon: Icons.close_rounded,
                      tooltip: 'مسح البحث',
                      onPressed: () {
                        _search.clear();
                        cubit.setText('');
                      },
                    ),
            ),
          ),
          const SizedBox(height: SahoolSpacing.sm),
          _FilterBar(state: state),
          const SizedBox(height: SahoolSpacing.sm),
          _Summary(state: state, visible: visible),
          if (showPriority) _PriorityNote(state: priorityState),
          if (visible.isEmpty)
            EmptyState(
              key: const ValueKey('fields_no_match'),
              icon: Icons.filter_alt_off_outlined,
              message: 'لا حقول تطابق البحث أو التصفية.',
              actionLabel: 'مسح الفلاتر',
              onAction: () {
                _search.clear();
                cubit.clearFilters();
              },
            )
          else
            for (final f in visible)
              FieldListCard(
                field: f,
                farmName: state.farmNames['${f['farm_id'] ?? ''}'],
                priority: showPriority ? byField[fieldIdOf(f)] : null,
                showPriority: showPriority,
                onTap: () => _openWorkspace(f),
              ),
        ],
      ),
    );
  }
}

class _Summary extends StatelessWidget {
  const _Summary({required this.state, required this.visible});
  final FieldsListState state;
  final List<Map<String, dynamic>> visible;

  @override
  Widget build(BuildContext context) {
    final areas = visible.map(fieldListArea);
    final known = areas.whereType<double>();
    final unknown = areas.length - known.length;
    final total = known.fold<double>(0, (a, b) => a + b);
    final parts = [
      '${visible.length} من ${state.all.length} حقل',
      if (known.isNotEmpty) 'المساحة ${fmtArea(total)}',
      if (unknown > 0) '$unknown بلا مساحة مقيسة',
    ];
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: SahoolSpacing.xs),
      child: Text(
        parts.join(' · '),
        key: const ValueKey('fields_summary'),
        style: context.textStyles.bodySmall,
      ),
    );
  }
}

class _PriorityNote extends StatelessWidget {
  const _PriorityNote({required this.state});
  final LoadState<PriorityData>? state;

  @override
  Widget build(BuildContext context) => switch (state) {
    LoadLoading() || null => const Padding(
      padding: EdgeInsets.symmetric(vertical: SahoolSpacing.sm),
      child: LinearProgressIndicator(),
    ),
    LoadFailed(:final error) => InlineError(
      error: error,
      onRetry: context.read<FieldsListCubit>().loadPriority,
    ),
    LoadLoaded(:final data) =>
      data.partial
          ? Text(
              'الأولويّة جزئيّة: تعذّر بعض المصادر — الحقول غير المقيسة في آخر القائمة.',
              style: context.textStyles.bodySmall,
            )
          : const SizedBox.shrink(),
  };
}

/// شريط التصفية والترتيب: أزرار كبيرة تفتح قوائم اختيار (لا كتابة).
class _FilterBar extends StatelessWidget {
  const _FilterBar({required this.state});
  final FieldsListState state;

  @override
  Widget build(BuildContext context) {
    final cubit = context.read<FieldsListCubit>();
    final q = state.query;
    String farmLabel(String id) =>
        id.isEmpty ? 'بلا مزرعة' : (state.farmNames[id] ?? 'مزرعة $id');
    String cropLabel(String c) => c.isEmpty ? 'بلا محصول' : c;
    String statusLabel(String s) => kQualityGradeAr[s] ?? s;
    return Wrap(
      spacing: SahoolSpacing.sm,
      runSpacing: SahoolSpacing.sm,
      children: [
        _ChoiceButton<FieldSort>(
          key: const ValueKey('fields_sort'),
          icon: Icons.sort_rounded,
          title: 'ترتيب حسب',
          label: q.sort.labelAr,
          active: true,
          options: {for (final s in FieldSort.values) s: s.labelAr},
          selected: q.sort,
          onSelected: (v) {
            if (v != null) cubit.setSort(v);
          },
        ),
        if (state.farmIds.length > 1)
          _ChoiceButton<String>(
            key: const ValueKey('fields_filter_farm'),
            icon: Icons.agriculture_outlined,
            title: 'المزرعة',
            label: q.farmId == null ? 'كلّ المزارع' : farmLabel(q.farmId!),
            active: q.farmId != null,
            options: {for (final id in state.farmIds) id: farmLabel(id)},
            selected: q.farmId,
            allLabel: 'كلّ المزارع',
            onSelected: cubit.setFarm,
          ),
        if (state.crops.length > 1)
          _ChoiceButton<String>(
            key: const ValueKey('fields_filter_crop'),
            icon: Icons.grass_outlined,
            title: 'المحصول',
            label: q.crop == null ? 'كلّ المحاصيل' : cropLabel(q.crop!),
            active: q.crop != null,
            options: {for (final c in state.crops) c: cropLabel(c)},
            selected: q.crop,
            allLabel: 'كلّ المحاصيل',
            onSelected: cubit.setCrop,
          ),
        if (state.statuses.isNotEmpty)
          _ChoiceButton<String>(
            key: const ValueKey('fields_filter_status'),
            icon: Icons.verified_outlined,
            title: 'الحالة',
            label: q.status == null ? 'كلّ الحالات' : statusLabel(q.status!),
            active: q.status != null,
            options: {for (final s in state.statuses) s: statusLabel(s)},
            selected: q.status,
            allLabel: 'كلّ الحالات',
            onSelected: cubit.setStatus,
          ),
      ],
    );
  }
}

/// زرّ يفتح ورقة اختيار. [allLabel] يضيف خيار «الكلّ» (null).
class _ChoiceButton<T> extends StatelessWidget {
  const _ChoiceButton({
    super.key,
    required this.icon,
    required this.title,
    required this.label,
    required this.active,
    required this.options,
    required this.selected,
    required this.onSelected,
    this.allLabel,
  });

  final IconData icon;
  final String title;
  final String label;
  final bool active;
  final Map<T, String> options;
  final T? selected;
  final ValueChanged<T?> onSelected;
  final String? allLabel;

  Future<void> _open(BuildContext context) async {
    final picked = await showAppBottomSheet<_Pick<T>>(
      context,
      builder: (ctx) => AppSheet(
        title: title,
        children: [
          if (allLabel != null)
            _tile(ctx, allLabel!, selected == null, const _Pick(null)),
          for (final e in options.entries)
            _tile(ctx, e.value, e.key == selected, _Pick(e.key)),
        ],
      ),
    );
    if (picked != null) onSelected(picked.value);
  }

  Widget _tile(BuildContext ctx, String text, bool on, _Pick<T> value) =>
      ListTile(
        minTileHeight: SahoolSizes.minTouchTarget,
        title: Text(text),
        trailing: on ? const Icon(Icons.check_rounded) : null,
        selected: on,
        onTap: () => Navigator.of(ctx).pop(value),
      );

  @override
  Widget build(BuildContext context) => FilterChip(
    avatar: Icon(icon, size: SahoolSizes.iconSm),
    label: Text(label, overflow: TextOverflow.ellipsis),
    selected: active,
    showCheckmark: false,
    materialTapTargetSize: MaterialTapTargetSize.padded,
    tooltip: title,
    onSelected: (_) => _open(context),
  );
}

class _Pick<T> {
  const _Pick(this.value);
  final T? value;
}

/// بطاقة حقل في القائمة: الاسم (يلتفّ ولا يفيض)، المحصول · المساحة · المزرعة،
/// حالة البيانات، وشارة الأولويّة حين الترتيب بها.
class FieldListCard extends StatelessWidget {
  const FieldListCard({
    super.key,
    required this.field,
    required this.onTap,
    this.farmName,
    this.priority,
    this.showPriority = false,
  });

  final Map<String, dynamic> field;
  final VoidCallback onTap;
  final String? farmName;
  final FieldPriority? priority;
  final bool showPriority;

  @override
  Widget build(BuildContext context) {
    final grade = wText(field['quality_grade'], '');
    final crop = cropOf(field);
    final p = priority;
    return Card(
      key: ValueKey('field_${fieldIdOf(field)}'),
      child: InkWell(
        onTap: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(
            minHeight: SahoolSizes.minTouchTarget,
          ),
          child: Padding(
            padding: const EdgeInsets.all(SahoolSpacing.lg),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        fieldNameOf(field),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: context.textStyles.titleMedium,
                      ),
                      const SizedBox(height: SahoolSpacing.xs),
                      Text(
                        [
                          crop ?? 'بلا محصول',
                          fmtArea(areaOf(field)),
                          ?farmName,
                        ].join(' · '),
                        style: context.textStyles.bodyMedium?.copyWith(
                          color: context.tokens.muted,
                        ),
                      ),
                      const SizedBox(height: SahoolSpacing.sm),
                      Wrap(
                        spacing: SahoolSpacing.sm,
                        runSpacing: SahoolSpacing.xs,
                        children: [
                          if (grade.isNotEmpty)
                            StatusChip(
                              label: kQualityGradeAr[grade] ?? grade,
                              tone: qualityTone(grade),
                            ),
                          if (showPriority)
                            StatusChip(
                              key: ValueKey('priority_${fieldIdOf(field)}'),
                              label: p == null
                                  ? 'الأولويّة غير مقيسة'
                                  : (p.count == 0
                                        ? 'لا تنبيهات أو مهامّ مفتوحة'
                                        : '${p.count} بنود مفتوحة · ${kSeverityAr[p.worstSeverity] ?? ''}'),
                              tone: p == null
                                  ? StatusTone.neutral
                                  : (p.count == 0
                                        ? StatusTone.success
                                        : severityTone(p.worstSeverity)),
                            ),
                        ],
                      ),
                    ],
                  ),
                ),
                Icon(Icons.chevron_right_rounded, color: context.tokens.muted),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
