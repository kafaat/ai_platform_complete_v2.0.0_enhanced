// SAHOOL — features/equipment/presentation/equipment_sheets.dart
// أوراق الكتابة في المعدّات: معدّة جديدة، وتسجيل صيانة (جدولة أو تنفيذ أو عطل).
// مفتاح Idempotency-Key واحد لعمر الورقة، تحقّق سطريّ داخلها (لا SnackBar تحتها)،
// أرقام عربيّة-هنديّة مقبولة، وزرّ حفظ مُقفَل أثناء الإرسال. تسجيل الصيانة عمل
// ميدانيّ: دون اتّصال يُودَع في صندوق الإرسال بنفس المفتاح أو يُقال إنّه غير متاح.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/equipment/data/equipment_api.dart';
import 'package:sahool_app/features/equipment/data/equipment_models.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';

enum EquipmentWriteResult { saved, queued }

String equipmentResultMessage(EquipmentWriteResult r, String savedText) =>
    r == EquipmentWriteResult.saved
    ? savedText
    : 'لا اتّصال: حُفظت العمليّة على الجهاز وستُرسَل عند عودة الشبكة.';

const String kEquipmentFixFields = 'راجع الحقول المعلَّمة باللون الأحمر.';

DateTime _day(DateTime d) => DateTime(d.year, d.month, d.day);

// ── معدّة جديدة ─────────────────────────────────────────────────────

class AddEquipmentSheet extends StatefulWidget {
  const AddEquipmentSheet({super.key, required this.api, this.today});
  final EquipmentApi api;
  final DateTime? today;

  @override
  State<AddEquipmentSheet> createState() => _AddEquipmentSheetState();
}

class _AddEquipmentSheetState extends State<AddEquipmentSheet> {
  final _form = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _hours = TextEditingController();
  final _notes = TextEditingController();
  final IdempotencyKey _key = IdempotencyKey.generate();
  String _type = 'tractor';
  DateTime? _purchase;
  bool _submitting = false;
  String? _error;

  @override
  void dispose() {
    _name.dispose();
    _hours.dispose();
    _notes.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_submitting) return;
    if (!(_form.currentState?.validate() ?? false)) {
      setState(() => _error = kEquipmentFixFields);
      return;
    }
    final hours = parseLocalizedNum(_hours.text);
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      await widget.api.createEquipment({
        'name': _name.text.trim(),
        'type': _type,
        if (hours != null) 'operating_hours': hours,
        if (_purchase != null) 'purchase_date': equipmentIsoDate(_purchase!),
        if (_notes.text.trim().isNotEmpty) 'notes': _notes.text.trim(),
      }, idempotencyKey: _key);
      if (!mounted) return;
      Navigator.of(context).pop(EquipmentWriteResult.saved);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _submitting = false;
        _error = ApiException.from(e).messageAr;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final today = _day(widget.today ?? DateTime.now());
    return Form(
      key: _form,
      child: AppSheet(
        title: 'معدّة جديدة',
        submitLabel: 'حفظ المعدّة',
        submitting: _submitting,
        onSubmit: _submit,
        errorText: _error,
        children: [
          AppDropdown<String>(
            label: 'النوع',
            items: kEquipmentTypes,
            value: _type,
            onChanged: (v) => setState(() => _type = v ?? 'other'),
          ),
          AppTextField(
            label: 'الاسم',
            hint: 'مثل: جرّار ماسي 290',
            controller: _name,
            validator: (v) => (v ?? '').trim().isEmpty ? 'الاسم مطلوب' : null,
          ),
          AppNumberField(
            label: 'ساعات التشغيل الحاليّة',
            controller: _hours,
            unit: 'ساعة',
            min: 0,
          ),
          OpsDateField(
            label: 'تاريخ الشراء (اختياري)',
            value: _purchase,
            firstDate: DateTime(today.year - 60),
            lastDate: today,
            onChanged: (d) => setState(() => _purchase = d),
          ),
          AppTextField(
            label: 'ملاحظات (اختياري)',
            controller: _notes,
            maxLines: 2,
          ),
        ],
      ),
    );
  }
}

// ── تسجيل صيانة ─────────────────────────────────────────────────────

class LogMaintenanceSheet extends StatefulWidget {
  const LogMaintenanceSheet({
    super.key,
    required this.api,
    required this.equipment,
    this.outbox,
    this.today,
  });

  final EquipmentApi api;
  final Equipment equipment;
  final OfflineOutbox? outbox;
  final DateTime? today;

  @override
  State<LogMaintenanceSheet> createState() => _LogMaintenanceSheetState();
}

class _LogMaintenanceSheetState extends State<LogMaintenanceSheet> {
  final _form = GlobalKey<FormState>();
  final _cost = TextEditingController();
  final _notes = TextEditingController();
  final IdempotencyKey _key = IdempotencyKey.generate();
  String _kind = 'scheduled';
  String _status = 'done';
  DateTime? _scheduled;
  DateTime? _performed;
  String? _scheduledError;
  String? _performedError;
  bool _submitting = false;
  String? _error;

  DateTime get _today => _day(widget.today ?? DateTime.now());

  @override
  void initState() {
    super.initState();
    _performed = _today;
  }

  @override
  void dispose() {
    _cost.dispose();
    _notes.dispose();
    super.dispose();
  }

  String get _path => '/api/v1/equipment/${widget.equipment.id}/maintenance';

  /// موعد بلا تاريخ ليس جدولة، وتنفيذ بلا تاريخ لا يُعرف متى تمّ.
  bool _validateDates() {
    setState(() {
      _scheduledError = _status == 'planned' && _scheduled == null
          ? 'حدّد موعد الصيانة المخطّطة'
          : null;
      _performedError = _status == 'done' && _performed == null
          ? 'حدّد تاريخ التنفيذ'
          : (_performed != null && _performed!.isAfter(_today)
                ? 'تاريخ التنفيذ لا يكون في المستقبل'
                : null);
    });
    return _scheduledError == null && _performedError == null;
  }

  Future<void> _submit() async {
    if (_submitting) return;
    final formOk = _form.currentState?.validate() ?? false;
    final datesOk = _validateDates();
    if (!formOk || !datesOk) {
      setState(() => _error = kEquipmentFixFields);
      return;
    }
    final cost = parseLocalizedNum(_cost.text);
    final body = <String, dynamic>{
      'kind': _kind,
      'status': _status,
      if (_scheduled != null) 'scheduled_date': equipmentIsoDate(_scheduled!),
      if (_status != 'planned' && _performed != null)
        'performed_date': equipmentIsoDate(_performed!),
      if (cost != null) 'cost_usd': cost,
      if (_notes.text.trim().isNotEmpty) 'notes': _notes.text.trim(),
    };
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      await widget.api.logMaintenance(
        widget.equipment.id,
        body,
        idempotencyKey: _key,
      );
      if (!mounted) return;
      Navigator.of(context).pop(EquipmentWriteResult.saved);
    } catch (e) {
      final err = ApiException.from(e);
      if (err.isConnectivity) {
        final receipt = await (widget.outbox ?? OfflineOutbox.instance).enqueue(
          OutboxOp(
            kind: 'equipment_maintenance_log',
            method: 'POST',
            path: _path,
            body: body,
            idempotencyKey: _key.value,
            labelAr: 'صيانة: ${widget.equipment.name}',
          ),
        );
        if (!mounted) return;
        if (receipt.queued) {
          Navigator.of(context).pop(EquipmentWriteResult.queued);
          return;
        }
        setState(() {
          _submitting = false;
          _error =
              '${err.messageAr}\nلم تُسجَّل الصيانة: الحفظ دون اتّصال غير '
              'متاح بعد على هذا الجهاز. أعِد المحاولة حين تعود الشبكة.';
        });
        return;
      }
      if (!mounted) return;
      setState(() {
        _submitting = false;
        _error = err.messageAr;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final today = _today;
    final marksBroken = _kind == 'breakdown' && _status != 'done';
    return Form(
      key: _form,
      child: AppSheet(
        title: 'تسجيل صيانة — ${widget.equipment.name}',
        submitLabel: 'حفظ السجلّ',
        submitting: _submitting,
        onSubmit: _submit,
        errorText: _error,
        children: [
          AppDropdown<String>(
            label: 'النوع',
            items: kMaintenanceKinds,
            value: _kind,
            onChanged: (v) => setState(() => _kind = v ?? 'scheduled'),
          ),
          AppDropdown<String>(
            label: 'الحالة',
            items: kMaintenanceStatuses,
            value: _status,
            onChanged: (v) => setState(() {
              _status = v ?? 'done';
              _scheduledError = null;
              _performedError = null;
            }),
          ),
          if (marksBroken)
            Padding(
              padding: const EdgeInsets.only(top: SahoolSpacing.sm),
              child: Text(
                'تسجيل عطل غير مُنجَز يجعل حالة المعدّة «معطّلة».',
                style: context.textStyles.bodySmall?.copyWith(
                  color: context.tokens.warning,
                ),
              ),
            ),
          OpsDateField(
            label: _status == 'planned'
                ? 'موعد الصيانة'
                : 'الموعد المخطّط (اختياري)',
            value: _scheduled,
            firstDate: DateTime(today.year - 5),
            lastDate: DateTime(today.year + 5),
            errorText: _scheduledError,
            onChanged: (d) => setState(() {
              _scheduled = d;
              _scheduledError = null;
            }),
          ),
          if (_status != 'planned')
            OpsDateField(
              label: 'تاريخ التنفيذ',
              value: _performed,
              firstDate: DateTime(today.year - 5),
              lastDate: today,
              errorText: _performedError,
              onChanged: (d) => setState(() {
                _performed = d;
                _performedError = null;
              }),
            ),
          AppNumberField(
            label: 'التكلفة (اختياري)',
            controller: _cost,
            unit: 'دولار أمريكي',
            min: 0,
          ),
          AppTextField(
            label: 'ملاحظات (اختياري)',
            hint: 'ما الذي فُحص أو أُصلح أو بُدّل',
            controller: _notes,
            maxLines: 3,
          ),
        ],
      ),
    );
  }
}
