// SAHOOL — features/scouting/presentation/new_observation_screen.dart
// «مشاهدة جديدة» مصمّمة ليد واحدة في الحقل: الموقع يُلتقط تلقائيّاً عند الفتح،
// الفئة والشدّة أزرار كبيرة بأيقونات، الملاحظة اختياريّة، وزرّ الحفظ ثابت أسفل
// الشاشة في متناول الإبهام. الصورة تبقى على الجهاز (لا تخزين صور في الخادم).
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

import '../data/device_sources.dart';
import '../data/scouting_models.dart';
import 'new_observation_cubit.dart';
import 'scouting_deps.dart';

const String kPhotoUploadUnavailable =
    'رفع الصور غير متاح بعد في الخادم — تبقى الصورة على هذا الجهاز فقط ولا تُرسل مع المشاهدة.';

class NewObservationScreen extends StatelessWidget {
  const NewObservationScreen({
    super.key,
    required this.field,
    this.deps,
    this.initialCategory,
    this.initialNote,
  });

  final ScoutingField field;
  final ScoutingDeps? deps;
  final IssueCategory? initialCategory;
  final String? initialNote;

  @override
  Widget build(BuildContext context) {
    final d = deps ?? ScoutingDeps.device();
    if (!d.canRecord) {
      return const AppScaffold(
        title: 'مشاهدة جديدة',
        body: EmptyState(
          icon: Icons.lock_outline_rounded,
          title: 'عرض فقط',
          message: 'دورك يسمح بعرض المشاهدات دون تسجيلها.',
        ),
      );
    }
    return BlocProvider(
      create: (_) => NewObservationCubit(
        field: field,
        api: d.api,
        location: d.location,
        photos: d.photos,
        photoStore: d.photoStore,
        outbox: d.outbox,
        connectivity: d.connectivity,
        initialCategory: initialCategory,
        initialNote: initialNote,
      )..start(),
      child: _NewObservationBody(field: field, initialNote: initialNote),
    );
  }
}

class _NewObservationBody extends StatefulWidget {
  const _NewObservationBody({required this.field, this.initialNote});
  final ScoutingField field;
  final String? initialNote;

  @override
  State<_NewObservationBody> createState() => _NewObservationBodyState();
}

class _NewObservationBodyState extends State<_NewObservationBody> {
  late final TextEditingController _note = TextEditingController(
    text: widget.initialNote ?? '',
  );

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  void _onOutcome(BuildContext context, NewObservationState s) {
    if (s.outcome != SubmitOutcome.sent && s.outcome != SubmitOutcome.queued) {
      return;
    }
    ScaffoldMessenger.maybeOf(
      context,
    )?.showSnackBar(SnackBar(content: Text(s.outcomeMessage ?? '')));
    Navigator.of(context).maybePop(true);
  }

  @override
  Widget build(BuildContext context) {
    final cubit = context.read<NewObservationCubit>();
    return BlocConsumer<NewObservationCubit, NewObservationState>(
      listenWhen: (a, b) => a.outcome != b.outcome,
      listener: _onOutcome,
      builder: (context, s) => AppScaffold(
        title: 'مشاهدة جديدة — ${widget.field.nameAr}',
        body: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Expanded(
              child: ListView(
                padding: const EdgeInsets.all(SahoolSpacing.md),
                children: [
                  _LocationCard(state: s, field: widget.field, cubit: cubit),
                  const SizedBox(height: SahoolSpacing.md),
                  _CategoryCard(state: s, cubit: cubit),
                  const SizedBox(height: SahoolSpacing.md),
                  _SeverityCard(state: s, cubit: cubit),
                  const SizedBox(height: SahoolSpacing.md),
                  SectionCard(
                    title: 'ملاحظات (اختياريّ)',
                    icon: Icons.notes_rounded,
                    child: AppTextField(
                      key: const ValueKey('scouting-note'),
                      label: 'ماذا لاحظت؟',
                      controller: _note,
                      maxLines: 3,
                      onChanged: cubit.setNote,
                      textInputAction: TextInputAction.done,
                    ),
                  ),
                  const SizedBox(height: SahoolSpacing.md),
                  _PhotoCard(state: s, cubit: cubit),
                ],
              ),
            ),
            _SubmitBar(state: s, onSubmit: cubit.submit),
          ],
        ),
      ),
    );
  }
}

class _ErrorLine extends StatelessWidget {
  const _ErrorLine(this.text);
  final String? text;
  @override
  Widget build(BuildContext context) {
    if (text == null) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: SahoolSpacing.sm),
      child: Text(
        text!,
        style: TextStyle(
          color: Theme.of(context).colorScheme.error,
          fontWeight: SahoolType.semibold,
        ),
      ),
    );
  }
}

class _LocationCard extends StatelessWidget {
  const _LocationCard({
    required this.state,
    required this.field,
    required this.cubit,
  });
  final NewObservationState state;
  final ScoutingField field;
  final NewObservationCubit cubit;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final s = state;
    final Widget status;
    switch (s.locationMode) {
      case LocationMode.locating:
        status = const Row(
          children: [
            SizedBox(
              width: 20,
              height: 20,
              child: CircularProgressIndicator(strokeWidth: 2.4),
            ),
            SizedBox(width: SahoolSpacing.sm),
            Expanded(child: Text('جارٍ تحديد موقعك بالـGPS…')),
          ],
        );
      case LocationMode.gps:
        final acc = s.accuracyM;
        final tone = acc == null
            ? StatusTone.neutral
            : acc <= 10
            ? StatusTone.success
            : acc <= 30
            ? StatusTone.warning
            : StatusTone.danger;
        status = Wrap(
          spacing: SahoolSpacing.sm,
          runSpacing: SahoolSpacing.sm,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            Text(_coords(s.lat!, s.lng!)),
            StatusChip(
              label: acc == null
                  ? 'الدقّة: $kNotMeasured'
                  : 'الدقّة ±${fmtNumber(acc, decimals: 0)} م',
              tone: tone,
              icon: Icons.gps_fixed_rounded,
            ),
          ],
        );
      case LocationMode.fieldCentre:
        status = Wrap(
          spacing: SahoolSpacing.sm,
          runSpacing: SahoolSpacing.sm,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            Text(_coords(s.lat!, s.lng!)),
            const StatusChip(
              label: 'مركز الحقل — ليس موقع المشاهدة المقيس',
              tone: StatusTone.warning,
              icon: Icons.center_focus_strong_outlined,
            ),
          ],
        );
      case LocationMode.failed:
      case LocationMode.none:
        status = Text(
          s.gpsFailure?.messageAr ?? 'لم يُحدَّد الموقع بعد.',
          style: TextStyle(color: t.muted),
        );
    }
    final failure = s.gpsFailure;
    final settings =
        failure != null &&
        (failure.reason == GpsFailureReason.deniedForever ||
            failure.reason == GpsFailureReason.serviceDisabled);
    return SectionCard(
      title: 'الموقع',
      icon: Icons.my_location_rounded,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          status,
          if (failure != null && s.hasLocation)
            Padding(
              padding: const EdgeInsets.only(top: SahoolSpacing.sm),
              child: Text(failure.messageAr, style: TextStyle(color: t.muted)),
            ),
          const SizedBox(height: SahoolSpacing.md),
          SecondaryButton(
            label: s.hasLocation ? 'إعادة التحديد بالـGPS' : 'تحديد بالـGPS',
            icon: Icons.gps_fixed_rounded,
            onPressed: s.locationMode == LocationMode.locating
                ? null
                : cubit.locate,
          ),
          const SizedBox(height: SahoolSpacing.sm),
          SecondaryButton(
            label: 'استخدم مركز الحقل',
            icon: Icons.center_focus_strong_outlined,
            onPressed: field.hasCenter ? cubit.useFieldCentre : null,
          ),
          if (!field.hasCenter)
            Padding(
              padding: const EdgeInsets.only(top: SahoolSpacing.xs),
              child: Text(
                'لا مركز مسجَّل لهذا الحقل على الخادم.',
                style: TextStyle(color: t.muted),
              ),
            ),
          if (settings) ...[
            const SizedBox(height: SahoolSpacing.sm),
            SecondaryButton(
              label: 'فتح الإعدادات',
              icon: Icons.settings_outlined,
              onPressed: cubit.openLocationSettings,
            ),
          ],
          _ErrorLine(s.errors[ObservationField.location]),
        ],
      ),
    );
  }

  static String _coords(double lat, double lng) =>
      '${lat.toStringAsFixed(6)}, ${lng.toStringAsFixed(6)}';
}

class _ChoiceTile extends StatelessWidget {
  const _ChoiceTile({
    super.key,
    required this.label,
    required this.icon,
    required this.selected,
    required this.onTap,
    this.color,
  });
  final String label;
  final IconData icon;
  final bool selected;
  final VoidCallback onTap;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final t = context.tokens;
    final accent = color ?? scheme.primary;
    return Semantics(
      button: true,
      selected: selected,
      label: label,
      excludeSemantics: true,
      child: Material(
        color: selected ? accent.withValues(alpha: 0.14) : t.surfaceAlt,
        shape: RoundedRectangleBorder(
          borderRadius: SahoolRadius.mdAll,
          side: BorderSide(
            color: selected ? accent : t.line,
            width: selected ? 2 : 1,
          ),
        ),
        child: InkWell(
          borderRadius: SahoolRadius.mdAll,
          onTap: onTap,
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 72),
            child: Padding(
              padding: const EdgeInsets.all(SahoolSpacing.sm),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    selected ? Icons.check_circle_rounded : icon,
                    color: selected ? accent : t.muted,
                    size: SahoolSizes.iconLg,
                  ),
                  const SizedBox(height: SahoolSpacing.xs),
                  Text(
                    label,
                    textAlign: TextAlign.center,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontWeight: selected
                          ? SahoolType.bold
                          : SahoolType.semibold,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _CategoryCard extends StatelessWidget {
  const _CategoryCard({required this.state, required this.cubit});
  final NewObservationState state;
  final NewObservationCubit cubit;

  @override
  Widget build(BuildContext context) {
    final issues = state.issuesForCategory;
    return SectionCard(
      title: 'نوع المشكلة',
      icon: Icons.category_outlined,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          GridView.count(
            crossAxisCount: 3,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            mainAxisSpacing: SahoolSpacing.sm,
            crossAxisSpacing: SahoolSpacing.sm,
            childAspectRatio: 1.05,
            children: [
              for (final c in IssueCategory.values)
                _ChoiceTile(
                  key: ValueKey('category-${c.wire}'),
                  label: c.labelAr,
                  icon: c.icon,
                  selected: state.category == c,
                  onTap: () => cubit.selectCategory(c),
                ),
            ],
          ),
          if (issues.isNotEmpty)
            AppDropdown<String>(
              key: ValueKey('issue-${state.category?.wire}'),
              label: 'المشكلة المحدّدة (اختياريّ)',
              items: {for (final i in issues) i.code: i.nameAr},
              value: state.issueCode,
              onChanged: cubit.selectIssue,
            ),
          _ErrorLine(state.errors[ObservationField.category]),
        ],
      ),
    );
  }
}

class _SeverityCard extends StatelessWidget {
  const _SeverityCard({required this.state, required this.cubit});
  final NewObservationState state;
  final NewObservationCubit cubit;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    Color colorOf(PinSeverity s) => switch (s) {
      PinSeverity.low => t.info,
      PinSeverity.medium => t.warning,
      PinSeverity.high => t.danger,
    };
    return SectionCard(
      title: 'الشدّة',
      icon: Icons.signal_cellular_alt_rounded,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              for (final s in PinSeverity.values) ...[
                if (s != PinSeverity.values.first)
                  const SizedBox(width: SahoolSpacing.sm),
                Expanded(
                  child: _ChoiceTile(
                    key: ValueKey('severity-${s.wire}'),
                    label: s.labelAr,
                    icon: s.icon,
                    color: colorOf(s),
                    selected: state.severity == s,
                    onTap: () => cubit.selectSeverity(s),
                  ),
                ),
              ],
            ],
          ),
          _ErrorLine(state.errors[ObservationField.severity]),
        ],
      ),
    );
  }
}

class _PhotoCard extends StatelessWidget {
  const _PhotoCard({required this.state, required this.cubit});
  final NewObservationState state;
  final NewObservationCubit cubit;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final path = state.photoPath;
    return SectionCard(
      title: 'صورة (اختياريّ)',
      icon: Icons.photo_camera_outlined,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (path != null) ...[
            ClipRRect(
              borderRadius: SahoolRadius.mdAll,
              child: Image.file(
                File(path),
                height: 160,
                fit: BoxFit.cover,
                errorBuilder: (_, _, _) => Container(
                  height: 64,
                  alignment: AlignmentDirectional.center,
                  child: Text(
                    'تعذّر عرض الصورة',
                    style: TextStyle(color: t.muted),
                  ),
                ),
              ),
            ),
            const SizedBox(height: SahoolSpacing.sm),
            SecondaryButton(
              label: 'حذف الصورة',
              icon: Icons.delete_outline_rounded,
              onPressed: cubit.removePhoto,
            ),
            const SizedBox(height: SahoolSpacing.sm),
          ],
          SecondaryButton(
            label: path == null ? 'التقاط صورة' : 'إعادة الالتقاط',
            icon: Icons.photo_camera_outlined,
            onPressed: () => cubit.capturePhoto(),
          ),
          const SizedBox(height: SahoolSpacing.sm),
          StatusChip(
            label: kPhotoUploadUnavailable,
            tone: StatusTone.info,
            icon: Icons.cloud_off_rounded,
          ),
          _ErrorLine(state.photoError),
        ],
      ),
    );
  }
}

class _SubmitBar extends StatelessWidget {
  const _SubmitBar({required this.state, required this.onSubmit});
  final NewObservationState state;
  final VoidCallback onSubmit;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final failed = state.outcome == SubmitOutcome.failed;
    return Material(
      color: t.surface,
      elevation: 6,
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.all(SahoolSpacing.md),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (failed && state.outcomeMessage != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: SahoolSpacing.sm),
                  child: StatusChip(
                    label: state.outcomeMessage!,
                    tone: StatusTone.danger,
                  ),
                ),
              if (state.errors.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(bottom: SahoolSpacing.sm),
                  child: Text(
                    'أكمل الحقول المطلوبة أعلاه.',
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                ),
              PrimaryButton(
                label: 'حفظ المشاهدة',
                icon: Icons.check_rounded,
                loading: state.submitting,
                onPressed: state.submitting ? null : onSubmit,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
