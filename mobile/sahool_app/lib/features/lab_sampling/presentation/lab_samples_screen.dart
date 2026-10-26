// SAHOOL — features/lab_sampling/presentation/lab_samples_screen.dart
// «عيّنات المختبر» لحقل: عدد ما ينتظر الإرسال دون اتّصال، جاهزيّة نتائج المختبر،
// ثمّ العيّنات بحالتها (جُمعت ← في المختبر ← وصلت النتيجة ← معتمدة/منشورة)
// وأزرار الانتقال المسموح بها. الكتابة تتطلّب field:edit (المالك والمدير).
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/crop_season/presentation/field_picker.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';

import '../data/lab_models.dart';
import '../data/lab_sampling_api.dart';
import 'gps_reader.dart';
import 'lab_results_screen.dart';
import 'lab_samples_cubit.dart';
import 'protocol_screen.dart';
import 'sample_create_screen.dart';

class LabSamplesScreen extends StatefulWidget {
  const LabSamplesScreen({
    super.key,
    this.fieldId,
    this.fieldName,
    this.areaHa,
    this.api,
    this.role,
    this.outbox,
    this.isOnline,
    this.gpsReader,
    this.fieldsLoader,
  });

  final String? fieldId;
  final String? fieldName;
  final double? areaHa;
  final LabSamplingApi? api;
  final String? role;
  final OfflineOutbox? outbox;
  final bool Function()? isOnline;
  final GpsReader? gpsReader;
  final FieldsLoader? fieldsLoader;

  @override
  State<LabSamplesScreen> createState() => _LabSamplesScreenState();
}

class _LabSamplesScreenState extends State<LabSamplesScreen> {
  FieldRef? _field;

  /// عدّاد صندوق الإرسال (اشتراك واحد طوال عمر الشاشة).
  int _pending = 0;
  StreamSubscription<int>? _pendingSub;

  @override
  void initState() {
    super.initState();
    final id = widget.fieldId;
    if (id != null && id.isNotEmpty) {
      _field = FieldRef(
        fieldId: id,
        nameAr: widget.fieldName,
        areaHa: widget.areaHa,
      );
    }
    _pendingSub = (widget.outbox ?? OfflineOutbox.instance).pendingCount.listen(
      (n) {
        if (mounted) setState(() => _pending = n);
      },
      onError: (Object _) {},
    );
  }

  @override
  void dispose() {
    _pendingSub?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final f = _field;
    if (f == null) {
      return AppScaffold(
        title: 'عيّنات المختبر',
        body: FieldPickerView(
          loader: widget.fieldsLoader,
          onPicked: (p) => setState(() => _field = p),
        ),
      );
    }
    return BlocProvider(
      key: ValueKey(f.fieldId),
      create: (_) =>
          LabSamplesCubit(widget.api ?? LabSamplingApi.instance, f.fieldId)
            ..load(),
      child: _LabSamplesView(
        field: f,
        widgetConfig: widget,
        pending: _pending,
        canWrite: canManage(widget.role ?? currentRole()),
      ),
    );
  }
}

StatusChip labStatusChip(LabSample s) {
  final st = s.status;
  final label =
      st?.labelAr ?? (s.statusRaw.isEmpty ? 'غير معروفة' : s.statusRaw);
  return switch (st) {
    LabSampleStatus.approved || LabSampleStatus.published => StatusChip(
      label: label,
      tone: StatusTone.success,
    ),
    LabSampleStatus.resultReceived => StatusChip(
      label: label,
      tone: StatusTone.info,
      icon: Icons.mark_email_read_outlined,
    ),
    LabSampleStatus.inLab => StatusChip(
      label: label,
      tone: StatusTone.info,
      icon: Icons.local_shipping_outlined,
    ),
    LabSampleStatus.rejected || LabSampleStatus.cancelled => StatusChip(
      label: label,
      tone: StatusTone.danger,
    ),
    _ => StatusChip(label: label, icon: Icons.inventory_2_outlined),
  };
}

class _LabSamplesView extends StatelessWidget {
  const _LabSamplesView({
    required this.field,
    required this.widgetConfig,
    required this.pending,
    required this.canWrite,
  });

  final FieldRef field;
  final LabSamplesScreen widgetConfig;
  final int pending;
  final bool canWrite;

  Future<void> _create(BuildContext context) async {
    final cubit = context.read<LabSamplesCubit>();
    final messenger = ScaffoldMessenger.of(context);
    final r = await Navigator.of(context).push<SampleCreateResult>(
      MaterialPageRoute(
        builder: (_) => SampleCreateScreen(
          fieldId: field.fieldId,
          fieldName: field.nameAr,
          areaHa: field.areaHa,
          api: widgetConfig.api,
          outbox: widgetConfig.outbox,
          isOnline: widgetConfig.isOnline,
          gpsReader: widgetConfig.gpsReader,
        ),
      ),
    );
    if (r == null) return;
    messenger.showSnackBar(
      SnackBar(
        content: Text(
          r == SampleCreateResult.sent
              ? 'حُفظت العيّنة'
              : 'حُفظت العيّنة على الجهاز وستُرسَل عند عودة الاتّصال',
        ),
      ),
    );
    if (r == SampleCreateResult.sent) await cubit.load();
  }

  Future<void> _transition(
    BuildContext context,
    LabSample s,
    LabTransitionAction a,
  ) async {
    final cubit = context.read<LabSamplesCubit>();
    final messenger = ScaffoldMessenger.of(context);
    if (a.destructive) {
      final ok = await showConfirmDialog(
        context,
        title: a.labelAr,
        message: a.target == LabSampleStatus.cancelled
            ? 'إلغاء العيّنة نهائيّ ولا يمكن التراجع عنه.'
            : 'سترجع العيّنة لإعادة الفحص أو الإلغاء.',
        confirmLabel: a.labelAr,
        destructive: true,
      );
      if (!ok) return;
    }
    final err = await cubit.transition(s, a.target);
    messenger.showSnackBar(
      SnackBar(content: Text(err ?? 'الحالة الآن: ${a.target.labelAr}')),
    );
  }

  @override
  Widget build(BuildContext context) {
    return BlocBuilder<LabSamplesCubit, LabSamplesState>(
      builder: (context, state) {
        final cubit = context.read<LabSamplesCubit>();
        return AppScaffold(
          title: 'عيّنات ${field.label}',
          onRefresh: cubit.load,
          actions: [
            AppIconButton(
              icon: Icons.menu_book_outlined,
              tooltip: 'إرشادات أخذ العيّنة',
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => ProtocolScreen(
                    areaHa: field.areaHa,
                    api: widgetConfig.api,
                  ),
                ),
              ),
            ),
            AppIconButton(
              icon: Icons.science_outlined,
              tooltip: 'نتائج المختبر',
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => LabResultsScreen(
                    fieldId: field.fieldId,
                    api: widgetConfig.api,
                  ),
                ),
              ),
            ),
          ],
          floatingActionButton: canWrite
              ? AppFab(
                  heroKey: '/lab-samples',
                  label: 'عيّنة جديدة',
                  icon: Icons.add_location_alt_outlined,
                  onPressed: () => _create(context),
                )
              : null,
          body: switch (state) {
            LabSamplesLoading() => const LoadingState(
              message: 'جارٍ تحميل العيّنات…',
            ),
            LabSamplesFailed(:final error) => ErrorState(
              error: error,
              onRetry: cubit.load,
            ),
            LabSamplesLoaded() => _loaded(context, state),
          },
        );
      },
    );
  }

  Widget _loaded(BuildContext context, LabSamplesLoaded s) {
    return ListView(
      padding: const EdgeInsetsDirectional.fromSTEB(
        SahoolSpacing.page,
        SahoolSpacing.md,
        SahoolSpacing.page,
        96,
      ),
      children: [
        if (pending > 0)
          Padding(
            padding: const EdgeInsetsDirectional.only(bottom: SahoolSpacing.md),
            child: StatusChip(
              label:
                  '${fmtNumber(pending, decimals: 0)} عمليّة بانتظار الإرسال',
              tone: StatusTone.warning,
              icon: Icons.cloud_upload_outlined,
            ),
          ),
        LabContextCard(ctx: s.context, error: s.contextError),
        const ListSectionHeader('العيّنات'),
        if (s.samples.isEmpty)
          EmptyState(
            title: 'لا عيّنات بعد',
            message: 'سجّل أوّل عيّنة تربة أو ماء من موقعها في الحقل.',
            icon: Icons.science_outlined,
            actionLabel: canWrite ? 'عيّنة جديدة' : null,
            onAction: canWrite ? () => _create(context) : null,
          ),
        for (final sample in s.samples)
          Padding(
            padding: const EdgeInsetsDirectional.only(bottom: SahoolSpacing.md),
            child: _SampleCard(
              sample: sample,
              busy: s.busy.contains(sample.sampleId),
              canWrite: canWrite,
              onAction: (a) => _transition(context, sample, a),
              onResults: () => Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => LabResultsScreen(
                    fieldId: field.fieldId,
                    api: widgetConfig.api,
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }
}

class _SampleCard extends StatelessWidget {
  const _SampleCard({
    required this.sample,
    required this.busy,
    required this.canWrite,
    required this.onAction,
    required this.onResults,
  });

  final LabSample sample;
  final bool busy;
  final bool canWrite;
  final ValueChanged<LabTransitionAction> onAction;
  final VoidCallback onResults;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final st = sample.status;
    final actions = canWrite
        ? labActionsFor(sample)
        : const <LabTransitionAction>[];
    Widget row(String label, String value) => Padding(
      padding: const EdgeInsetsDirectional.only(top: SahoolSpacing.xs),
      child: Row(
        children: [
          Expanded(
            child: Text(
              label,
              style: context.textStyles.bodyMedium?.copyWith(color: t.muted),
            ),
          ),
          Flexible(
            child: Text(
              value,
              textAlign: TextAlign.end,
              style: context.textStyles.bodyMedium,
            ),
          ),
        ],
      ),
    );
    final depth = sample.depthFromCm != null && sample.depthToCm != null
        ? '${fmtNumber(sample.depthFromCm, decimals: 0)}–${fmtNumber(sample.depthToCm, decimals: 0)} سم'
        : '—';
    final coords = sample.latitude != null && sample.longitude != null
        ? '${sample.latitude!.toStringAsFixed(5)}, ${sample.longitude!.toStringAsFixed(5)}'
        : '—';
    return SectionCard(
      title: sample.isSoil ? 'عيّنة تربة' : 'عيّنة ماء',
      icon: sample.isSoil
          ? Icons.landscape_outlined
          : Icons.water_drop_outlined,
      trailing: labStatusChip(sample),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          row('المعرّف', sample.sampleId),
          row('تاريخ الجمع', fmtIsoDate(sample.sampledOn)),
          if (sample.isSoil) row('العمق', depth),
          row('الموقع', coords),
          if (sample.gpsAccuracyM != null)
            row(
              'دقّة GPS',
              '± ${fmtNumber(sample.gpsAccuracyM, decimals: 0)} م',
            ),
          if (sample.source != null) row('المصدر', sample.source!),
          if (st == LabSampleStatus.inLab)
            Padding(
              padding: const EdgeInsetsDirectional.only(top: SahoolSpacing.sm),
              child: Text(
                'بانتظار نتيجة المختبر',
                style: context.textStyles.bodyMedium?.copyWith(color: t.info),
              ),
            ),
          if (st == LabSampleStatus.resultReceived ||
              st == LabSampleStatus.approved ||
              st == LabSampleStatus.published)
            Align(
              alignment: AlignmentDirectional.centerStart,
              child: TextButton.icon(
                onPressed: onResults,
                icon: const Icon(Icons.science_outlined),
                label: const Text('عرض النتائج'),
              ),
            ),
          if (actions.isNotEmpty) ...[
            const SizedBox(height: SahoolSpacing.md),
            if (busy)
              const LinearProgressIndicator()
            else
              Wrap(
                spacing: SahoolSpacing.sm,
                runSpacing: SahoolSpacing.sm,
                children: [
                  for (final a in actions)
                    SecondaryButton(
                      label: a.labelAr,
                      expand: false,
                      onPressed: () => onAction(a),
                    ),
                ],
              ),
          ],
        ],
      ),
    );
  }
}
