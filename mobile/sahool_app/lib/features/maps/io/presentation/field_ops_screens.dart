// SAHOOL — features/maps/io/presentation/field_ops_screens.dart
// شاشتا الدمج والتقسيم. كلتاهما: معاينة من الخادم على الخريطة ← تأكيد صريح (العمليّة
// تحذف الحقول المصدر) ← التزام ذرّيّ بمفتاح Idempotency.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

import '../data/maps_io_api.dart';
import '../geo/io_geometry.dart';
import 'field_ops_cubit.dart';
import 'io_map.dart';

Widget _previewStatus(BuildContext context, FieldOpsState s) {
  switch (s.preview) {
    case PreviewPhase.loading:
      return const StatusChip(
        label: 'جارٍ حساب المعاينة في الخادم…',
        tone: StatusTone.info,
      );
    case PreviewPhase.disabled:
      return StatusChip(label: s.previewError!, tone: StatusTone.warning);
    case PreviewPhase.failed:
      return StatusChip(
        label: s.previewError ?? 'تعذّرت المعاينة',
        tone: StatusTone.danger,
      );
    case PreviewPhase.ready:
      return const StatusChip(
        label: 'معاينة من الخادم — لم يُحفظ شيء بعد',
        tone: StatusTone.success,
      );
    case PreviewPhase.none:
      return const SizedBox.shrink();
  }
}

Widget _commitError(BuildContext context, FieldOpsState s) =>
    s.commit == CommitPhase.failed && s.commitError != null
    ? Padding(
        padding: const EdgeInsets.only(top: SahoolSpacing.sm),
        child: Semantics(
          liveRegion: true,
          child: Text(
            s.commitError!,
            style: context.textStyles.bodyMedium?.copyWith(
              color: context.tokens.danger,
            ),
          ),
        ),
      )
    : const SizedBox.shrink();

Widget _done(BuildContext context, String message) => EmptyState(
  icon: Icons.check_circle_outline_rounded,
  title: 'تمّ',
  message: message,
  actionLabel: 'العودة',
  onAction: () => Navigator.of(context).maybePop(true),
);

// ─── الدمج ──────────────────────────────────────────────────────────────

class MergeFieldsScreen extends StatelessWidget {
  const MergeFieldsScreen({super.key, this.api, this.showBasemap = true});
  final MapsIoApi? api;
  final bool showBasemap;

  @override
  Widget build(BuildContext context) => BlocProvider(
    create: (_) => MergeCubit(api ?? MapsIoApi.instance)..load(),
    child: _MergeView(showBasemap: showBasemap),
  );
}

class _MergeView extends StatefulWidget {
  const _MergeView({required this.showBasemap});
  final bool showBasemap;
  @override
  State<_MergeView> createState() => _MergeViewState();
}

class _MergeViewState extends State<_MergeView> {
  final _name = TextEditingController();
  String? _nameError;

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  Future<void> _commit(BuildContext context, FieldOpsState s) async {
    final name = _name.text.trim();
    if (name.isEmpty) {
      setState(() => _nameError = 'اسم الحقل المدموج مطلوب');
      return;
    }
    setState(() => _nameError = null);
    final names = s.selectedFields.map((f) => '«${f.name}»').join(' و');
    final ok = await showConfirmDialog(
      context,
      title: 'دمج الحقلين؟',
      message:
          'سيُنشأ «$name» ويُحذف $names نهائيّاً. لا يتمّ الدمج إن كان على '
          'أحدهما موسم نشط.',
      confirmLabel: 'دمج',
      destructive: true,
    );
    if (!ok || !context.mounted) return;
    await context.read<MergeCubit>().commit(name);
  }

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      title: 'دمج حقلين',
      body: BlocBuilder<MergeCubit, FieldOpsState>(
        builder: (context, s) {
          final cubit = context.read<MergeCubit>();
          if (s.loading) {
            return const LoadingState(message: 'جارٍ تحميل الحقول');
          }
          if (s.loadError != null) {
            return ErrorState(error: s.loadError!, onRetry: cubit.load);
          }
          if (s.commit == CommitPhase.done) {
            return _done(context, 'دُمج الحقلان في «${_name.text.trim()}».');
          }
          if (s.fields.length < 2) {
            return const EmptyState(
              icon: Icons.merge_type_rounded,
              message: 'الدمج يحتاج حقلين على الأقلّ لهما حدود محفوظة.',
            );
          }
          final sel = s.selectedFields;
          return Column(
            children: [
              SizedBox(
                height: 240,
                child: IoMap(
                  showBasemap: widget.showBasemap,
                  shapes: [
                    if (s.preview == PreviewPhase.ready)
                      for (final p in polygonsFromGeoJson(s.resultGeometry))
                        IoMapShape(p, label: 'المدموج')
                    else
                      for (final f in s.fields)
                        for (final p in f.polygons)
                          IoMapShape(
                            p,
                            selected: s.selected.contains(f.id),
                            label: f.name,
                          ),
                  ],
                ),
              ),
              Expanded(
                child: ListView(
                  padding: const EdgeInsets.all(SahoolSpacing.page),
                  children: [
                    Text(
                      'اختر حقلين متجاورين (${sel.length}/2)',
                      style: context.textStyles.titleMedium,
                    ),
                    for (final f in s.fields)
                      CheckboxListTile(
                        value: s.selected.contains(f.id),
                        onChanged: s.commit == CommitPhase.saving
                            ? null
                            : (_) => cubit.toggle(f.id),
                        title: Text(f.name),
                        subtitle: Text(fmtArea(f.areaHa, decimals: 2)),
                        controlAffinity: ListTileControlAffinity.leading,
                      ),
                    const SizedBox(height: SahoolSpacing.sm),
                    _previewStatus(context, s),
                    if (s.preview == PreviewPhase.ready &&
                        s.resultGeometry?['type'] == 'MultiPolygon')
                      const Padding(
                        padding: EdgeInsets.only(top: SahoolSpacing.sm),
                        child: StatusChip(
                          label:
                              'الحقلان غير متلاصقين — سيُحفظ المدموج من جزأين منفصلين.',
                          tone: StatusTone.warning,
                        ),
                      ),
                    const SizedBox(height: SahoolSpacing.md),
                    if (s.preview != PreviewPhase.ready)
                      PrimaryButton(
                        label: 'معاينة الدمج',
                        icon: Icons.visibility_outlined,
                        loading: s.preview == PreviewPhase.loading,
                        onPressed: s.selected.length == 2
                            ? cubit.preview
                            : null,
                      )
                    else ...[
                      AppTextField(
                        label: 'اسم الحقل المدموج',
                        controller: _name,
                        errorText: _nameError,
                        enabled: s.commit != CommitPhase.saving,
                      ),
                      _commitError(context, s),
                      const SizedBox(height: SahoolSpacing.md),
                      PrimaryButton(
                        label: 'دمج وحفظ',
                        icon: Icons.merge_type_rounded,
                        tone: ButtonTone.danger,
                        loading: s.commit == CommitPhase.saving,
                        onPressed: () => _commit(context, s),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

// ─── التقسيم ────────────────────────────────────────────────────────────

class SplitFieldScreen extends StatelessWidget {
  const SplitFieldScreen({
    super.key,
    this.api,
    this.fieldId,
    this.showBasemap = true,
  });
  final MapsIoApi? api;
  final String? fieldId;
  final bool showBasemap;

  @override
  Widget build(BuildContext context) => BlocProvider(
    create: (_) =>
        SplitCubit(api ?? MapsIoApi.instance)..load(preselect: fieldId),
    child: _SplitView(showBasemap: showBasemap),
  );
}

class _SplitView extends StatefulWidget {
  const _SplitView({required this.showBasemap});
  final bool showBasemap;
  @override
  State<_SplitView> createState() => _SplitViewState();
}

class _SplitViewState extends State<_SplitView> {
  final List<TextEditingController> _names = [];
  String? _nameError;

  @override
  void dispose() {
    for (final c in _names) {
      c.dispose();
    }
    super.dispose();
  }

  void _syncNames(FieldOpsState s) {
    if (_names.length == s.parts.length) return;
    for (final c in _names) {
      c.dispose();
    }
    _names
      ..clear()
      ..addAll([
        for (var i = 0; i < s.parts.length; i++)
          TextEditingController(
            text: '${s.selectedFields.firstOrNull?.name ?? 'حقل'} — ${i + 1}',
          ),
      ]);
  }

  Future<void> _commit(BuildContext context, FieldOpsState s) async {
    final names = _names.map((c) => c.text.trim()).toList();
    final lower = names.map((n) => n.toLowerCase()).toSet();
    if (names.any((n) => n.isEmpty) || lower.length != names.length) {
      setState(() => _nameError = 'لكلّ جزء اسم مطلوب ومختلف عن غيره.');
      return;
    }
    setState(() => _nameError = null);
    final src = s.selectedFields.first;
    final ok = await showConfirmDialog(
      context,
      title: 'تقسيم الحقل؟',
      message:
          'سيُنشأ ${names.length} حقول ويُحذف «${src.name}» نهائيّاً. لا يتمّ '
          'التقسيم إن كان عليه موسم نشط.',
      confirmLabel: 'تقسيم',
      destructive: true,
    );
    if (!ok || !context.mounted) return;
    await context.read<SplitCubit>().commit(names);
  }

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      title: 'تقسيم حقل',
      body: BlocConsumer<SplitCubit, FieldOpsState>(
        listener: (_, s) => setState(() => _syncNames(s)),
        listenWhen: (a, b) => a.parts.length != b.parts.length,
        builder: (context, s) {
          final cubit = context.read<SplitCubit>();
          if (s.loading) {
            return const LoadingState(message: 'جارٍ تحميل الحقول');
          }
          if (s.loadError != null) {
            return ErrorState(error: s.loadError!, onRetry: cubit.load);
          }
          if (s.commit == CommitPhase.done) {
            return _done(context, 'قُسم الحقل إلى ${s.parts.length} حقول.');
          }
          if (s.fields.isEmpty) {
            return const EmptyState(
              icon: Icons.content_cut_rounded,
              message: 'لا حقول لها حدود محفوظة لتقسيمها.',
            );
          }
          if (s.selected.isEmpty) {
            return ListView(
              padding: const EdgeInsets.all(SahoolSpacing.page),
              children: [
                Text(
                  'اختر الحقل المراد تقسيمه',
                  style: context.textStyles.titleMedium,
                ),
                for (final f in s.fields)
                  AppListTile(
                    title: f.name,
                    subtitle: fmtArea(f.areaHa, decimals: 2),
                    icon: Icons.crop_square_rounded,
                    onTap: () => cubit.choose(f.id),
                  ),
              ],
            );
          }
          final src = s.selectedFields.first;
          final ready = s.preview == PreviewPhase.ready;
          return Column(
            children: [
              Expanded(
                flex: 5,
                child: IoMap(
                  showBasemap: widget.showBasemap,
                  onTap: ready ? null : cubit.addBladePoint,
                  shapes: ready
                      ? [
                          for (var i = 0; i < s.parts.length; i++)
                            for (final p in polygonsFromGeoJson(s.parts[i]))
                              IoMapShape(
                                p,
                                label: '${i + 1}',
                                selected: i.isEven,
                              ),
                        ]
                      : [
                          for (final p in src.polygons)
                            IoMapShape(p, label: src.name),
                        ],
                  lines: [if (s.blade.length >= 2) s.blade],
                  points: s.blade,
                ),
              ),
              Expanded(
                flex: 6,
                child: ListView(
                  padding: const EdgeInsets.all(SahoolSpacing.page),
                  children: [
                    Text(
                      ready
                          ? 'الأجزاء الناتجة (${s.parts.length}) — سمِّ كلّ جزء.'
                          : 'المس الخريطة لرسم خطّ القطع: نقطة خارج الحدّ، ثمّ نقطة '
                                'خارجه من الجهة الأخرى (${s.blade.length} نقطة).',
                      style: context.textStyles.bodyLarge,
                    ),
                    const SizedBox(height: SahoolSpacing.sm),
                    _previewStatus(context, s),
                    if (!ready) ...[
                      const SizedBox(height: SahoolSpacing.md),
                      Row(
                        children: [
                          Expanded(
                            child: SecondaryButton(
                              label: 'تراجع',
                              icon: Icons.undo_rounded,
                              onPressed: s.blade.isEmpty
                                  ? null
                                  : cubit.undoBladePoint,
                            ),
                          ),
                          const SizedBox(width: SahoolSpacing.sm),
                          Expanded(
                            child: SecondaryButton(
                              label: 'مسح الخطّ',
                              icon: Icons.clear_rounded,
                              onPressed: s.blade.isEmpty
                                  ? null
                                  : cubit.clearBlade,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: SahoolSpacing.md),
                      PrimaryButton(
                        label: 'معاينة التقسيم',
                        icon: Icons.visibility_outlined,
                        loading: s.preview == PreviewPhase.loading,
                        onPressed: s.blade.length >= 2 ? cubit.preview : null,
                      ),
                    ] else ...[
                      for (var i = 0; i < _names.length; i++)
                        AppTextField(
                          label: 'اسم الجزء ${i + 1}',
                          controller: _names[i],
                          enabled: s.commit != CommitPhase.saving,
                        ),
                      if (_nameError != null)
                        Padding(
                          padding: const EdgeInsets.only(top: SahoolSpacing.sm),
                          child: Text(
                            _nameError!,
                            style: context.textStyles.bodyMedium?.copyWith(
                              color: context.tokens.danger,
                            ),
                          ),
                        ),
                      _commitError(context, s),
                      const Padding(
                        padding: EdgeInsets.only(top: SahoolSpacing.sm),
                        child: StatusChip(
                          label:
                              'الحقول الناتجة لا تُربط بمزرعة الأصل (حدّ في الخادم).',
                          tone: StatusTone.info,
                        ),
                      ),
                      const SizedBox(height: SahoolSpacing.md),
                      PrimaryButton(
                        label: 'تقسيم وحفظ',
                        icon: Icons.content_cut_rounded,
                        tone: ButtonTone.danger,
                        loading: s.commit == CommitPhase.saving,
                        onPressed: () => _commit(context, s),
                      ),
                      const SizedBox(height: SahoolSpacing.sm),
                      SecondaryButton(
                        label: 'تعديل الخطّ',
                        icon: Icons.edit_rounded,
                        onPressed: s.commit == CommitPhase.saving
                            ? null
                            : cubit.clearBlade,
                      ),
                    ],
                  ],
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}
