// SAHOOL — features/irrigation/presentation/ledger/water_ledger_screen.dart
// دفتر المياه اليوميّ لحقل: آخر 30 يوماً (ريّ · مطر · ETc · استنزاف) + تسجيل
// الماء المضاف (field:edit — المالك والمدير). القيمة الغائبة «غير مقيس» لا صفر.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/irrigation/data/irrigation_api.dart';
import 'package:sahool_app/features/irrigation/data/irrigation_models.dart';
import 'package:sahool_app/features/irrigation/presentation/irrigation_format.dart';
import 'package:sahool_app/features/irrigation/presentation/ledger/log_water_sheet.dart';
import 'package:sahool_app/features/irrigation/presentation/ledger/water_ledger_cubit.dart';

class WaterLedgerScreen extends StatelessWidget {
  const WaterLedgerScreen({
    super.key,
    required this.fieldId,
    this.fieldName,
    this.areaHa,
    this.api,
    this.role,
    this.cubitFactory,
  });

  final String fieldId;
  final String? fieldName;
  final num? areaHa;
  final IrrigationApi? api;

  /// للاختبار؛ null ⇒ دور الجلسة.
  final String? role;

  /// للاختبار (حقن الاتّصال والطابور).
  final WaterLedgerCubit Function()? cubitFactory;

  @override
  Widget build(BuildContext context) => BlocProvider(
    create: (_) =>
        (cubitFactory?.call() ??
              WaterLedgerCubit(api ?? IrrigationApi.instance, fieldId))
          ..load(),
    child: _WaterLedgerView(
      fieldName: fieldName,
      areaHa: areaHa,
      canWrite: canWriteWaterLedger(role ?? currentRole()),
    ),
  );
}

class _WaterLedgerView extends StatelessWidget {
  const _WaterLedgerView({
    required this.fieldName,
    required this.areaHa,
    required this.canWrite,
  });

  final String? fieldName;
  final num? areaHa;
  final bool canWrite;

  Future<void> _log(BuildContext context) async {
    final cubit = context.read<WaterLedgerCubit>();
    final msg = await showLogWaterSheet(context, cubit: cubit, areaHa: areaHa);
    if (msg != null && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final cubit = context.read<WaterLedgerCubit>();
    return AppScaffold(
      title: fieldName == null ? 'دفتر المياه' : 'دفتر المياه — $fieldName',
      actions: [
        AppIconButton(
          icon: Icons.refresh_rounded,
          tooltip: 'تحديث',
          onPressed: cubit.load,
        ),
      ],
      floatingActionButton: canWrite
          ? AppFab(
              heroKey: 'irrigation-ledger',
              label: 'سجّل ريّاً',
              icon: Icons.add_rounded,
              onPressed: () => _log(context),
            )
          : null,
      body: BlocBuilder<WaterLedgerCubit, WaterLedgerState>(
        builder: (context, s) => switch (s) {
          WaterLedgerLoading() => const LoadingState(
            message: 'جارٍ تحميل دفتر المياه…',
          ),
          WaterLedgerFailed(:final error) => ErrorState(
            error: error,
            onRetry: cubit.load,
          ),
          WaterLedgerLoaded() => RefreshIndicator(
            onRefresh: cubit.load,
            child: ListView(
              padding: const EdgeInsetsDirectional.fromSTEB(
                SahoolSpacing.page,
                SahoolSpacing.md,
                SahoolSpacing.page,
                SahoolSpacing.xxl * 3,
              ),
              children: [
                if (!canWrite)
                  Padding(
                    padding: const EdgeInsetsDirectional.only(
                      bottom: SahoolSpacing.md,
                    ),
                    child: Text(
                      'تسجيل الريّ في الدفتر للمالك والمدير فقط.',
                      style: context.textStyles.bodySmall,
                    ),
                  ),
                if (s.noteAr != null)
                  Padding(
                    padding: const EdgeInsetsDirectional.only(
                      bottom: SahoolSpacing.md,
                    ),
                    child: StatusChip(
                      label: s.noteAr!,
                      tone: StatusTone.warning,
                    ),
                  ),
                if (s.entries.isEmpty)
                  SizedBox(
                    height: 360,
                    child: EmptyState(
                      message:
                          'لا قيود في آخر ${WaterLedgerCubit.historyDays} يوماً.',
                      icon: Icons.water_drop_outlined,
                    ),
                  )
                else
                  for (final e in s.entries) _LedgerTile(e, areaHa: areaHa),
              ],
            ),
          ),
        },
      ),
    );
  }
}

class _LedgerTile extends StatelessWidget {
  const _LedgerTile(this.e, {this.areaHa});
  final WaterLedgerEntry e;
  final num? areaHa;

  @override
  Widget build(BuildContext context) {
    final irr = e.knownIrrigationMm;
    final m3 = mmToM3(irr, areaHa);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(SahoolSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    e.date == null ? e.ledgerDate : fmtDate(e.date),
                    style: context.textStyles.titleSmall,
                  ),
                ),
                StatusChip(
                  label: e.isAuto ? 'آليّ' : 'يدويّ',
                  tone: e.isAuto ? StatusTone.neutral : StatusTone.info,
                  icon: e.isAuto
                      ? Icons.smart_toy_outlined
                      : Icons.person_outline_rounded,
                ),
              ],
            ),
            const SizedBox(height: SahoolSpacing.sm),
            Text(
              'الريّ: ${irr == null ? 'غير مسجَّل' : fmtMm(irr)}'
              '${m3 != null ? ' (≈ ${fmtM3(m3, decimals: 0)})' : ''}'
              '${e.irrigationVolumeUntracked ? ' — أدنى تقدير (حجم غير مسجَّل)' : ''}',
              style: context.textStyles.bodyLarge,
            ),
            const SizedBox(height: SahoolSpacing.xs),
            Text(
              'المطر: ${fmtMm(e.rainMm)} · ETc: ${fmtMm(e.etcMm)} · الاستنزاف: ${fmtMm(e.depletionMm)}',
              style: context.textStyles.bodySmall,
            ),
          ],
        ),
      ),
    );
  }
}
