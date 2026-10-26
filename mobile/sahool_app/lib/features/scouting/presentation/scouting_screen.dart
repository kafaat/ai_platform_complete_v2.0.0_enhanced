// SAHOOL — features/scouting/presentation/scouting_screen.dart
// الاستكشاف الميدانيّ: اختيار الحقل ← دبابيسه (قائمة أو خريطة) بمرشّحات النوع
// والشدّة والتاريخ ← «مشاهدة جديدة» (للأدوار المعدِّلة) و«كشف الآفات بالصورة».
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

import '../data/scouting_models.dart';
import 'new_observation_screen.dart';
import 'pest_detect_screen.dart';
import 'pins_cubit.dart';
import 'pins_map.dart';
import 'scouting_deps.dart';
import 'scouting_fields_cubit.dart';
import 'scouting_widgets.dart';

class ScoutingScreen extends StatelessWidget {
  const ScoutingScreen({super.key, this.initialFieldId, this.deps});

  final String? initialFieldId;
  final ScoutingDeps? deps;

  @override
  Widget build(BuildContext context) {
    final d = deps ?? ScoutingDeps.device();
    return BlocProvider(
      create: (_) => ScoutingFieldsCubit(loader: d.fieldsLoader)..load(),
      child: _ScoutingBody(deps: d, initialFieldId: initialFieldId),
    );
  }
}

class _ScoutingBody extends StatefulWidget {
  const _ScoutingBody({required this.deps, this.initialFieldId});
  final ScoutingDeps deps;
  final String? initialFieldId;

  @override
  State<_ScoutingBody> createState() => _ScoutingBodyState();
}

class _ScoutingBodyState extends State<_ScoutingBody> {
  String? _fieldId;

  @override
  void initState() {
    super.initState();
    _fieldId = widget.initialFieldId;
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<ScoutingFieldsCubit>().state;
    final fieldsCubit = context.read<ScoutingFieldsCubit>();
    ScoutingField? field;
    if (state is ScoutingFieldsLoaded) {
      field = state.byId(_fieldId);
      // حقل واحد ⇒ لا خطوة اختيار.
      if (field == null && _fieldId == null && state.fields.length == 1) {
        field = state.fields.first;
      }
    }
    final title = field == null
        ? 'الاستكشاف الميدانيّ'
        : 'الاستكشاف — ${field.nameAr}';
    final f = field;
    return AppScaffold(
      title: title,
      actions: [
        if (f != null &&
            state is ScoutingFieldsLoaded &&
            state.fields.length > 1)
          AppIconButton(
            icon: Icons.swap_horiz_rounded,
            tooltip: 'تغيير الحقل',
            onPressed: () => setState(() => _fieldId = ''),
          ),
        if (f != null && widget.deps.canRecord)
          AppIconButton(
            icon: Icons.camera_alt_outlined,
            tooltip: 'كشف الآفات بالصورة',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) => PestDetectScreen(field: f, deps: widget.deps),
              ),
            ),
          ),
      ],
      body: switch (state) {
        ScoutingFieldsLoading() => const LoadingState(
          message: 'جارٍ تحميل الحقول…',
        ),
        ScoutingFieldsFailed(:final error) => ErrorState(
          error: error,
          onRetry: fieldsCubit.load,
        ),
        ScoutingFieldsLoaded(:final fields) =>
          f == null
              ? FieldChoiceList(
                  fields: fields,
                  missingId: _fieldId,
                  onChoose: (c) => setState(() => _fieldId = c.id),
                )
              : PinsView(key: ValueKey(f.id), field: f, deps: widget.deps),
      },
    );
  }
}

enum _PinsMode { list, map }

/// دبابيس حقل واحد (قائمة/خريطة) + المرشّحات + زرّ «مشاهدة جديدة».
class PinsView extends StatelessWidget {
  const PinsView({super.key, required this.field, required this.deps});
  final ScoutingField field;
  final ScoutingDeps deps;

  @override
  Widget build(BuildContext context) => BlocProvider(
    create: (_) => PinsCubit(deps.api, field.id)..load(),
    child: _PinsBody(field: field, deps: deps),
  );
}

class _PinsBody extends StatefulWidget {
  const _PinsBody({required this.field, required this.deps});
  final ScoutingField field;
  final ScoutingDeps deps;

  @override
  State<_PinsBody> createState() => _PinsBodyState();
}

class _PinsBodyState extends State<_PinsBody> {
  _PinsMode _mode = _PinsMode.list;

  Future<void> _newObservation() async {
    final cubit = context.read<PinsCubit>();
    final saved = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) =>
            NewObservationScreen(field: widget.field, deps: widget.deps),
      ),
    );
    if (saved == true && mounted) await cubit.load();
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<PinsCubit>().state;
    final cubit = context.read<PinsCubit>();
    return Stack(
      children: [
        Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(
                SahoolSpacing.lg,
                SahoolSpacing.md,
                SahoolSpacing.lg,
                0,
              ),
              child: SegmentedButton<_PinsMode>(
                segments: const [
                  ButtonSegment(
                    value: _PinsMode.list,
                    icon: Icon(Icons.list_rounded),
                    label: Text('قائمة'),
                  ),
                  ButtonSegment(
                    value: _PinsMode.map,
                    icon: Icon(Icons.map_outlined),
                    label: Text('خريطة'),
                  ),
                ],
                selected: {_mode},
                onSelectionChanged: (s) => setState(() => _mode = s.first),
              ),
            ),
            _FiltersBar(filters: state.filters, onChanged: cubit.setFilters),
            Expanded(child: _content(context, state, cubit)),
          ],
        ),
        if (widget.deps.canRecord)
          PositionedDirectional(
            end: SahoolSpacing.lg,
            bottom: SahoolSpacing.lg,
            child: AppFab(
              heroKey: 'scouting-new',
              label: 'مشاهدة جديدة',
              icon: Icons.add_location_alt_outlined,
              onPressed: _newObservation,
            ),
          ),
      ],
    );
  }

  Widget _content(BuildContext context, PinsState state, PinsCubit cubit) {
    final page = state.page;
    if (page == null) {
      return switch (state.status) {
        PinsStatus.failed => ErrorState(
          error: state.error!,
          onRetry: cubit.load,
        ),
        _ => const LoadingState(message: 'جارٍ تحميل المشاهدات…'),
      };
    }
    final visible = state.visible(DateTime.now());
    final banner = <Widget>[
      if (state.status == PinsStatus.loading)
        const LinearProgressIndicator(minHeight: 2),
      if (state.status == PinsStatus.failed && state.error != null)
        Padding(
          padding: const EdgeInsets.all(SahoolSpacing.md),
          child: StatusChip(
            label:
                'تعذّر التحديث: ${state.error!.messageAr} — المعروض آخر ما وصل.',
            tone: StatusTone.warning,
          ),
        ),
      if (page.noteAr != null)
        Padding(
          padding: const EdgeInsets.all(SahoolSpacing.md),
          child: StatusChip(label: page.noteAr!, tone: StatusTone.info),
        ),
    ];
    Widget body;
    if (page.pins.isEmpty) {
      body = EmptyState(
        icon: Icons.place_outlined,
        title: 'لا مشاهدات بعد',
        message: page.noteAr != null
            ? 'لا دبابيس مُخزَّنة على الخادم لهذا الحقل.'
            : 'لم تُسجَّل مشاهدات لهذا الحقل بعد.',
        actionLabel: widget.deps.canRecord ? 'مشاهدة جديدة' : null,
        onAction: widget.deps.canRecord ? _newObservation : null,
      );
    } else if (visible.isEmpty) {
      body = EmptyState(
        icon: Icons.filter_alt_off_outlined,
        message: 'لا مشاهدات تطابق المرشّحات المختارة.',
        actionLabel: 'مسح المرشّحات',
        onAction: () => cubit.setFilters(const PinFilters()),
      );
    } else if (_mode == _PinsMode.map) {
      body = ScoutingPinsMap(
        pins: visible,
        field: widget.field,
        showTiles: widget.deps.showMapTiles,
        onPinTap: (p) => showPinDetails(context, p, widget.deps),
      );
    } else {
      body = RefreshIndicator(
        onRefresh: cubit.load,
        child: ListView.builder(
          padding: const EdgeInsetsDirectional.only(bottom: 96),
          itemCount: visible.length,
          itemBuilder: (_, i) => PinTile(
            pin: visible[i],
            onTap: () => showPinDetails(context, visible[i], widget.deps),
          ),
        ),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ...banner,
        Expanded(child: body),
      ],
    );
  }
}

class _FiltersBar extends StatelessWidget {
  const _FiltersBar({required this.filters, required this.onChanged});
  final PinFilters filters;
  final ValueChanged<PinFilters> onChanged;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    Widget menu<T>({
      required String label,
      required String? current,
      required List<(T?, String)> options,
      required ValueChanged<T?> onSelect,
      required IconData icon,
    }) => PopupMenuButton<int>(
      tooltip: label,
      onSelected: (i) => onSelect(options[i].$1),
      itemBuilder: (_) => [
        for (var i = 0; i < options.length; i++)
          PopupMenuItem<int>(value: i, child: Text(options[i].$2)),
      ],
      child: Container(
        constraints: const BoxConstraints(
          minHeight: SahoolSizes.minTouchTarget,
        ),
        padding: const EdgeInsetsDirectional.symmetric(
          horizontal: SahoolSpacing.md,
        ),
        decoration: BoxDecoration(
          border: Border.all(color: current == null ? t.line : t.info),
          borderRadius: const BorderRadius.all(
            Radius.circular(SahoolRadius.pill),
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: SahoolSizes.iconSm),
            const SizedBox(width: SahoolSpacing.xs),
            Text(current ?? label),
            const Icon(Icons.arrow_drop_down_rounded),
          ],
        ),
      ),
    );

    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.all(SahoolSpacing.md),
      child: Row(
        children: [
          menu<IssueCategory>(
            label: 'كلّ الأنواع',
            current: filters.category?.labelAr,
            icon: Icons.category_outlined,
            options: [
              (null, 'كلّ الأنواع'),
              for (final c in IssueCategory.values) (c, c.labelAr),
            ],
            onSelect: (c) => onChanged(
              PinFilters(
                category: c,
                severity: filters.severity,
                window: filters.window,
              ),
            ),
          ),
          const SizedBox(width: SahoolSpacing.sm),
          menu<PinSeverity>(
            label: 'كلّ الشدّات',
            current: filters.severity?.labelAr,
            icon: Icons.signal_cellular_alt_rounded,
            options: [
              (null, 'كلّ الشدّات'),
              for (final s in PinSeverity.values) (s, s.labelAr),
            ],
            onSelect: (s) => onChanged(
              PinFilters(
                category: filters.category,
                severity: s,
                window: filters.window,
              ),
            ),
          ),
          const SizedBox(width: SahoolSpacing.sm),
          menu<PinsDateWindow>(
            label: PinsDateWindow.all.labelAr,
            current: filters.window == PinsDateWindow.all
                ? null
                : filters.window.labelAr,
            icon: Icons.date_range_outlined,
            options: [for (final w in PinsDateWindow.values) (w, w.labelAr)],
            onSelect: (w) => onChanged(
              PinFilters(
                category: filters.category,
                severity: filters.severity,
                window: w ?? PinsDateWindow.all,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
