// SAHOOL — features/maps/io/presentation/gps_walk_screen.dart
// مشي حدود الحقل: تيّار موقع مستمرّ مع مرشّح دقّة، إيقاف/استئناف، المسافة
// والمساحة حيّتين، وتبسيط المسار عند الإنهاء. ثمّ: حفظه حقلاً (format=gps) لمن
// يملك إنشاء الحقول، أو إعادته مضلّعاً لتدفّق الرسم ([pickMode]: `Navigator.pop`
// بـGeoJSON Polygon `Map<String, dynamic>`).
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

import '../data/maps_io_api.dart';
import '../geo/io_geometry.dart';
import '../geo/io_measure.dart';
import '../gps/gps_save_cubit.dart';
import '../gps/gps_walk_cubit.dart';
import '../gps/location_source.dart';
import 'io_map.dart';

String fmtMeters(num? m) {
  if (m == null) return kNotMeasured;
  if (m >= 1000) return '${fmtNumber(m / 1000, decimals: 2)} كم';
  return '${fmtNumber(m, decimals: 0)} م';
}

class GpsWalkScreen extends StatelessWidget {
  const GpsWalkScreen({
    super.key,
    this.api,
    this.source,
    this.farmId,
    this.pickMode = false,
    this.canSave,
    this.showBasemap = true,
  });

  final MapsIoApi? api;
  final LocationSource? source;
  final String? farmId;
  final bool pickMode;

  /// null ⇒ من دور الجلسة (owner/manager يملكان إنشاء الحقول في الخادم).
  final bool? canSave;
  final bool showBasemap;

  @override
  Widget build(BuildContext context) => MultiBlocProvider(
    providers: [
      BlocProvider(create: (_) => GpsWalkCubit(source: source)),
      BlocProvider(
        create: (_) => GpsSaveCubit(api ?? MapsIoApi.instance, farmId: farmId),
      ),
    ],
    child: _GpsWalkView(
      pickMode: pickMode,
      canSave: canSave ?? canManage(currentRole()),
      showBasemap: showBasemap,
    ),
  );
}

class _GpsWalkView extends StatefulWidget {
  const _GpsWalkView({
    required this.pickMode,
    required this.canSave,
    required this.showBasemap,
  });
  final bool pickMode;
  final bool canSave;
  final bool showBasemap;

  @override
  State<_GpsWalkView> createState() => _GpsWalkViewState();
}

class _GpsWalkViewState extends State<_GpsWalkView> {
  final _name = TextEditingController();
  String? _nameError;

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  Future<void> _confirmReset(BuildContext context) async {
    final ok = await showConfirmDialog(
      context,
      title: 'بدء مسار جديد؟',
      message: 'ستُحذف كلّ النقاط المسجّلة في هذا المسار.',
      confirmLabel: 'حذف المسار',
      destructive: true,
    );
    if (!ok || !context.mounted) return;
    context.read<GpsWalkCubit>().reset();
    context.read<GpsSaveCubit>().reset();
  }

  Future<void> _save(BuildContext context, GpsWalkState s) async {
    final name = _name.text.trim();
    if (name.isEmpty) {
      setState(() => _nameError = 'اسم الحقل مطلوب');
      return;
    }
    setState(() => _nameError = null);
    await context.read<GpsSaveCubit>().save(
      name: name,
      ring: s.simplified,
      rawVertexCount: s.track.length,
      toleranceM: s.toleranceM,
    );
  }

  @override
  Widget build(BuildContext context) {
    return BlocBuilder<GpsWalkCubit, GpsWalkState>(
      builder: (context, s) {
        final saved =
            context.watch<GpsSaveCubit>().state.phase == SavePhase.saved;
        return PopScope(
          canPop: s.track.isEmpty || saved,
          onPopInvokedWithResult: (didPop, _) async {
            if (didPop) return;
            final leave = await showConfirmDialog(
              context,
              title: 'مغادرة دون حفظ؟',
              message: 'المسار المسجّل (${s.track.length} نقطة) سيُفقد.',
              confirmLabel: 'مغادرة',
              destructive: true,
            );
            if (leave && context.mounted) {
              context.read<GpsWalkCubit>().reset();
              Navigator.of(context).pop();
            }
          },
          child: AppScaffold(
            title: 'مشي حدود الحقل',
            body: Column(
              children: [
                Expanded(
                  flex: 5,
                  child: IoMap(
                    showBasemap: widget.showBasemap,
                    follow: s.phase == GpsWalkPhase.recording,
                    here: s.lastFix,
                    hereAccuracyM: s.lastAccuracyM,
                    shapes: [
                      if (s.phase == GpsWalkPhase.finished &&
                          s.simplified.length >= 3)
                        IoMapShape(IoPolygon([s.simplified])),
                    ],
                    lines: [
                      if (s.phase != GpsWalkPhase.finished &&
                          s.track.length >= 2)
                        s.track,
                    ],
                    dashedClosure:
                        s.phase != GpsWalkPhase.finished && s.track.length >= 3
                        ? [s.track.last, s.track.first]
                        : null,
                  ),
                ),
                Expanded(
                  flex: 6,
                  child: ListView(
                    padding: const EdgeInsets.all(SahoolSpacing.page),
                    children: [
                      _Metrics(s: s),
                      const SizedBox(height: SahoolSpacing.md),
                      ..._controls(context, s),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  List<Widget> _controls(BuildContext context, GpsWalkState s) {
    final cubit = context.read<GpsWalkCubit>();
    final muted = context.textStyles.bodyMedium?.copyWith(
      color: context.tokens.muted,
    );
    switch (s.phase) {
      case GpsWalkPhase.idle:
      case GpsWalkPhase.starting:
        return [
          Text(
            'قف عند إحدى زوايا الحقل، ثمّ امشِ على الحدّ حتّى تعود إليها. '
            'أبقِ الشاشة مفتوحة أثناء المشي.',
            style: muted,
          ),
          const SizedBox(height: SahoolSpacing.md),
          _AccuracyPicker(
            value: s.maxAccuracyM,
            onChanged: cubit.setMaxAccuracy,
          ),
          const SizedBox(height: SahoolSpacing.lg),
          PrimaryButton(
            label: 'ابدأ المشي',
            icon: Icons.directions_walk_rounded,
            loading: s.phase == GpsWalkPhase.starting,
            onPressed: cubit.start,
          ),
        ];
      case GpsWalkPhase.recording:
      case GpsWalkPhase.paused:
        final recording = s.phase == GpsWalkPhase.recording;
        return [
          if (s.lastVerdict != null)
            StatusChip(
              label: s.lastVerdict!.messageAr,
              tone: s.lastVerdict == FixVerdict.accepted
                  ? StatusTone.success
                  : (s.lastVerdict == FixVerdict.tooClose
                        ? StatusTone.neutral
                        : StatusTone.warning),
            ),
          if (!recording) ...[
            const SizedBox(height: SahoolSpacing.sm),
            const StatusChip(
              label: 'متوقّف مؤقّتاً — لا تُسجَّل قراءات',
              tone: StatusTone.info,
            ),
            const SizedBox(height: SahoolSpacing.sm),
            _AccuracyPicker(
              value: s.maxAccuracyM,
              onChanged: cubit.setMaxAccuracy,
            ),
          ],
          const SizedBox(height: SahoolSpacing.md),
          Row(
            children: [
              Expanded(
                child: SecondaryButton(
                  label: recording ? 'إيقاف مؤقّت' : 'استئناف',
                  icon: recording
                      ? Icons.pause_rounded
                      : Icons.play_arrow_rounded,
                  onPressed: recording ? cubit.pause : cubit.resume,
                ),
              ),
              const SizedBox(width: SahoolSpacing.sm),
              Expanded(
                child: SecondaryButton(
                  label: 'تراجع عن نقطة',
                  icon: Icons.undo_rounded,
                  onPressed: s.track.isEmpty ? null : cubit.undoLast,
                ),
              ),
            ],
          ),
          const SizedBox(height: SahoolSpacing.md),
          PrimaryButton(
            label: s.track.length < 3
                ? 'إنهاء (يحتاج 3 نقاط)'
                : 'إنهاء وإغلاق الحدّ',
            icon: Icons.flag_rounded,
            onPressed: s.track.length < 3 ? null : cubit.finish,
          ),
        ];
      case GpsWalkPhase.finished:
        return _finished(context, s);
      case GpsWalkPhase.serviceDisabled:
        return _blocked(
          context,
          'خدمة الموقع مُطفأة على الجهاز — فعّلها ثمّ أعِد المحاولة.',
          settings: 'فتح إعدادات الموقع',
        );
      case GpsWalkPhase.permissionDenied:
        return _blocked(
          context,
          'إذن الموقع مرفوض — لا يمكن تسجيل المسار دونه.',
        );
      case GpsWalkPhase.permissionDeniedForever:
        return _blocked(
          context,
          'إذن الموقع مرفوض نهائيّاً — اسمح به من إعدادات التطبيق.',
          settings: 'فتح إعدادات التطبيق',
        );
      case GpsWalkPhase.failed:
        return _blocked(context, s.errorMessage ?? 'تعذّر تشغيل الموقع.');
    }
  }

  List<Widget> _blocked(
    BuildContext context,
    String message, {
    String? settings,
  }) {
    final cubit = context.read<GpsWalkCubit>();
    return [
      StatusChip(label: message, tone: StatusTone.danger),
      const SizedBox(height: SahoolSpacing.md),
      if (settings != null) ...[
        SecondaryButton(
          label: settings,
          icon: Icons.settings_outlined,
          onPressed: cubit.openSettings,
        ),
        const SizedBox(height: SahoolSpacing.sm),
      ],
      PrimaryButton(
        label: 'إعادة المحاولة',
        icon: Icons.refresh_rounded,
        onPressed: () {
          cubit.reset();
          cubit.start();
        },
      ),
    ];
  }

  List<Widget> _finished(BuildContext context, GpsWalkState s) {
    final cubit = context.read<GpsWalkCubit>();
    final save = context.watch<GpsSaveCubit>().state;
    final ring = s.simplified;
    final issues = validateForSave(IoPolygon([ring]));
    final blocked = issues.any((i) => i.blocking);
    final muted = context.textStyles.bodySmall?.copyWith(
      color: context.tokens.muted,
    );
    if (save.phase == SavePhase.saved) {
      return [
        const StatusChip(
          label: 'أُنشئ الحقل من مسار المشي',
          tone: StatusTone.success,
        ),
        const SizedBox(height: SahoolSpacing.lg),
        PrimaryButton(
          label: 'تمّ',
          icon: Icons.check_rounded,
          onPressed: () => Navigator.of(context).maybePop(true),
        ),
      ];
    }
    return [
      Text('تبسيط الحدود', style: context.textStyles.titleMedium),
      const SizedBox(height: SahoolSpacing.sm),
      Wrap(
        spacing: SahoolSpacing.sm,
        children: [
          for (final t in const [1.0, 3.0, 5.0])
            ChoiceChip(
              label: Text('${fmtNumber(t, decimals: 0)} م'),
              selected: s.toleranceM == t,
              onSelected: save.phase == SavePhase.saving
                  ? null
                  : (_) => cubit.setTolerance(t),
            ),
        ],
      ),
      const SizedBox(height: SahoolSpacing.xs),
      Text(
        '${s.track.length} نقطة مسجّلة ← ${ring.length} رأس بعد التبسيط '
        '(يُحذف ما ينحرف أقلّ من ${fmtNumber(s.toleranceM, decimals: 0)} م عن الخطّ).',
        style: muted,
      ),
      for (final i in issues)
        Padding(
          padding: const EdgeInsets.only(top: SahoolSpacing.sm),
          child: StatusChip(
            label: i.messageAr,
            tone: i.blocking ? StatusTone.danger : StatusTone.warning,
          ),
        ),
      const SizedBox(height: SahoolSpacing.md),
      if (widget.pickMode)
        PrimaryButton(
          label: 'استخدم الحدّ في الرسم',
          icon: Icons.check_rounded,
          onPressed: blocked
              ? null
              : () => Navigator.of(
                  context,
                ).pop(polygonToGeoJson(IoPolygon([ring]))),
        )
      else if (widget.canSave) ...[
        AppTextField(
          label: 'اسم الحقل',
          controller: _name,
          errorText: _nameError,
          enabled: save.phase != SavePhase.saving,
        ),
        if (save.phase == SavePhase.failed && save.error != null)
          Padding(
            padding: const EdgeInsets.only(top: SahoolSpacing.sm),
            child: Semantics(
              liveRegion: true,
              child: Text(
                save.error!,
                style: context.textStyles.bodyMedium?.copyWith(
                  color: context.tokens.danger,
                ),
              ),
            ),
          ),
        const SizedBox(height: SahoolSpacing.md),
        PrimaryButton(
          label: save.phase == SavePhase.failed
              ? 'إعادة محاولة الحفظ'
              : 'حفظ كحقل',
          icon: Icons.cloud_upload_outlined,
          loading: save.phase == SavePhase.saving,
          onPressed: blocked ? null : () => _save(context, s),
        ),
      ] else
        const StatusChip(
          label: 'إنشاء الحقول للمالك والمدير فقط — المساحة أعلاه للاطّلاع.',
          tone: StatusTone.info,
        ),
      const SizedBox(height: SahoolSpacing.sm),
      Row(
        children: [
          Expanded(
            child: SecondaryButton(
              label: 'متابعة المشي',
              icon: Icons.directions_walk_rounded,
              onPressed: save.phase == SavePhase.saving
                  ? null
                  : cubit.continueWalking,
            ),
          ),
          const SizedBox(width: SahoolSpacing.sm),
          Expanded(
            child: SecondaryButton(
              label: 'مسار جديد',
              icon: Icons.delete_outline_rounded,
              onPressed: save.phase == SavePhase.saving
                  ? null
                  : () => _confirmReset(context),
            ),
          ),
        ],
      ),
    ];
  }
}

class _Metrics extends StatelessWidget {
  const _Metrics({required this.s});
  final GpsWalkState s;

  @override
  Widget build(BuildContext context) {
    final finished = s.phase == GpsWalkPhase.finished;
    final area = finished
        ? (s.simplified.length >= 3
              ? polygonAreaHa(IoPolygon([s.simplified]))
              : null)
        : s.areaHa;
    return Wrap(
      spacing: SahoolSpacing.sm,
      runSpacing: SahoolSpacing.sm,
      children: [
        _metric(context, 'النقاط', fmtNumber(s.track.length, decimals: 0)),
        _metric(context, 'مرفوضة', fmtNumber(s.rejected, decimals: 0)),
        _metric(
          context,
          'الدقّة الآن',
          s.lastAccuracyM == null
              ? kNotMeasured
              : '±${fmtMeters(s.lastAccuracyM)}',
        ),
        _metric(
          context,
          'المسافة',
          fmtMeters(s.track.isEmpty ? null : s.distanceM),
        ),
        _metric(
          context,
          'المساحة',
          area == null ? kNotMeasured : fmtArea(area, decimals: 2),
        ),
      ],
    );
  }

  Widget _metric(BuildContext context, String label, String value) => Container(
    constraints: const BoxConstraints(minWidth: 96),
    padding: const EdgeInsetsDirectional.all(SahoolSpacing.sm),
    decoration: BoxDecoration(
      border: Border.all(color: context.tokens.line),
      borderRadius: SahoolRadius.smAll,
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: context.textStyles.bodySmall?.copyWith(
            color: context.tokens.muted,
          ),
        ),
        Text(value, style: context.textStyles.titleMedium),
      ],
    ),
  );
}

class _AccuracyPicker extends StatelessWidget {
  const _AccuracyPicker({required this.value, required this.onChanged});
  final double value;
  final ValueChanged<double> onChanged;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Text('أقصى خطأ مقبول للقراءة', style: context.textStyles.titleSmall),
      const SizedBox(height: SahoolSpacing.xs),
      Wrap(
        spacing: SahoolSpacing.sm,
        children: [
          for (final m in const [5.0, 10.0, 15.0, 20.0])
            ChoiceChip(
              label: Text('${fmtNumber(m, decimals: 0)} م'),
              selected: value == m,
              onSelected: (_) => onChanged(m),
            ),
        ],
      ),
    ],
  );
}
