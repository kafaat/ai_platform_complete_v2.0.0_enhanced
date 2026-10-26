// SAHOOL — features/irrigation/presentation/ledger/log_water_sheet.dart
// نموذج «سجّل الماء المضاف»: يوم (اليوم افتراضاً، حتّى 30 يوماً للخلف) + كمّيّة
// بالمليمتر أو بالمتر المكعّب (إن عُرفت مساحة الحقل). مفتاح نيّة واحد يُولَّد عند
// فتح الورقة ويُعاد في كلّ محاولة. الإيصال صادق: محفوظ / في الطابور / لم يُحفَظ.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/irrigation/presentation/irrigation_format.dart';
import 'package:sahool_app/features/irrigation/presentation/ledger/water_ledger_cubit.dart';

const String kQueuedMessage =
    'لا اتّصال — حُفظ القيد في طابور الإرسال وسيُرسَل عند عودة الشبكة.';
const String kSavedMessage = 'حُفظ الماء المضاف في دفتر المياه.';
const String kNotQueuedMessage =
    'لا اتّصال، ولم يُحفَظ القيد: الحفظ دون اتّصال غير متاح بعد على هذا الجهاز. '
    'أبقِ النموذج مفتوحاً وأعد المحاولة عند عودة الشبكة.';

/// يفتح الورقة ويُرجع رسالة النجاح/الطابور (null ⇒ أُغلقت بلا حفظ).
Future<String?> showLogWaterSheet(
  BuildContext context, {
  required WaterLedgerCubit cubit,
  num? areaHa,
  DateTime? today,
}) => showAppBottomSheet<String>(
  context,
  builder: (_) => LogWaterSheet(cubit: cubit, areaHa: areaHa, today: today),
);

class LogWaterSheet extends StatefulWidget {
  const LogWaterSheet({
    super.key,
    required this.cubit,
    this.areaHa,
    this.today,
  });

  final WaterLedgerCubit cubit;
  final num? areaHa;
  final DateTime? today;

  @override
  State<LogWaterSheet> createState() => _LogWaterSheetState();
}

class _LogWaterSheetState extends State<LogWaterSheet> {
  final _amount = TextEditingController();
  late final IdempotencyKey _key = IdempotencyKey.generate();
  late final DateTime _today = _dateOnly(widget.today ?? widget.cubit.now());
  late DateTime _date = _today;
  WaterUnit _unit = WaterUnit.mm;
  String? _fieldError;
  String? _submitError;
  bool _submitting = false;

  static DateTime _dateOnly(DateTime d) => DateTime(d.year, d.month, d.day);

  bool get _areaKnown => widget.areaHa != null && widget.areaHa! > 0;

  @override
  void dispose() {
    _amount.dispose();
    super.dispose();
  }

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _date,
      firstDate: _today.subtract(
        const Duration(days: WaterLedgerCubit.historyDays),
      ),
      lastDate: _today,
      helpText: 'يوم الريّ',
    );
    if (picked != null && mounted) setState(() => _date = _dateOnly(picked));
  }

  Future<void> _submit() async {
    if (_submitting) return;
    final v = validateAppliedWater(
      _amount.text,
      unit: _unit,
      areaHa: widget.areaHa,
    );
    if (v.error != null) {
      setState(() {
        _fieldError = v.error;
        _submitError = null;
      });
      return;
    }
    setState(() {
      _fieldError = null;
      _submitError = null;
      _submitting = true;
    });
    final result = await widget.cubit.logAppliedWater(
      ledgerDate: isoDay(_date),
      irrigationMm: v.mm!,
      key: _key,
    );
    if (!mounted) return;
    switch (result) {
      case WaterLogSaved():
        Navigator.of(context).pop(kSavedMessage);
      case WaterLogQueued():
        Navigator.of(context).pop(kQueuedMessage);
      case WaterLogNotQueued():
        setState(() {
          _submitting = false;
          _submitError = kNotQueuedMessage;
        });
      case WaterLogFailed(:final error):
        setState(() {
          _submitting = false;
          _submitError = refusalText(error);
        });
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = widget.cubit.state;
    final existing = state is WaterLedgerLoaded
        ? state.forDate(isoDay(_date))
        : null;
    final mmPreview = validateAppliedWater(
      _amount.text,
      unit: _unit,
      areaHa: widget.areaHa,
    ).mm;
    return AppSheet(
      title: 'سجّل الماء المضاف',
      submitLabel: 'حفظ في الدفتر',
      onSubmit: _submit,
      submitting: _submitting,
      errorText: _submitError,
      children: [
        const SizedBox(height: SahoolSpacing.sm),
        Text(
          'أدخل إجماليّ ماء الريّ لهذا اليوم. يُستبدَل به أيّ رقم ريّ سابق لنفس اليوم.',
          style: context.textStyles.bodyMedium,
        ),
        const SizedBox(height: SahoolSpacing.md),
        SizedBox(
          height: SahoolSizes.minTouchTarget,
          child: OutlinedButton.icon(
            onPressed: _submitting ? null : _pickDate,
            icon: const Icon(Icons.event_rounded),
            label: Text('اليوم: ${fmtDate(_date)}'),
          ),
        ),
        if (_areaKnown) ...[
          const SizedBox(height: SahoolSpacing.md),
          SegmentedButton<WaterUnit>(
            segments: const [
              ButtonSegment(value: WaterUnit.mm, label: Text('مم')),
              ButtonSegment(value: WaterUnit.m3, label: Text('م³')),
            ],
            selected: {_unit},
            onSelectionChanged: _submitting
                ? null
                : (s) => setState(() {
                    _unit = s.first;
                    _fieldError = null;
                  }),
          ),
        ],
        AppTextField(
          label: _unit == WaterUnit.mm ? 'الكمّيّة (مم)' : 'الحجم (م³)',
          controller: _amount,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          inputFormatters: const [LocalizedDigitsFormatter()],
          errorText: _fieldError,
          enabled: !_submitting,
          onChanged: (_) => setState(() => _fieldError = null),
          helper: _unit == WaterUnit.m3 && mmPreview != null
              ? '≈ ${fmtMm(mmPreview, decimals: 2)} على ${fmtNumber(widget.areaHa)} هـ'
              : (_areaKnown && mmPreview != null
                    ? '≈ ${fmtM3(mmToM3(mmPreview, widget.areaHa), decimals: 0)}'
                    : null),
        ),
        if (existing != null && existing.knownIrrigationMm != null) ...[
          const SizedBox(height: SahoolSpacing.md),
          Text(
            'مسجَّل لهذا اليوم: ${fmtMm(existing.knownIrrigationMm)} — سيُستبدَل بالقيمة الجديدة.',
            style: context.textStyles.bodySmall?.copyWith(
              color: context.tokens.warning,
            ),
          ),
        ],
        const SizedBox(height: SahoolSpacing.md),
        Text(
          'تُحفَظ قيم الطقس والاستنزاف التي حسبها الخادم لهذا اليوم كما هي؛ '
          'إعادة حساب الاستنزاف بالريّ المسجَّل غير متاحة بعد في الخادم.',
          style: context.textStyles.bodySmall,
        ),
      ],
    );
  }
}
