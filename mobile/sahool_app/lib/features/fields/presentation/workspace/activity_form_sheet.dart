// SAHOOL — features/fields/presentation/workspace/activity_form_sheet.dart
// ورقة «تسجيل نشاط» (POST /api/v1/fields/{id}/activities) خلف زرّ لا فوق السجلّ.
// مفتاح Idempotency-Key واحد لكلّ فتح للورقة، وزرّ الحفظ يمنع الإرسال المزدوج،
// والأخطاء داخل الورقة. التاريخ يُعرَض بالعربيّة ويُرسَل YYYY-MM-DD محلّيّاً.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';

/// أنواع النشاط المسموح إدخالها من الموبايل (activity_type ← التسمية).
const Map<String, String> kLoggableActivityTypes = {
  'irrigation': 'ريّ',
  'fertilization': 'تسميد',
  'spraying': 'رشّ',
  'scouting': 'كشف ميدانيّ',
  'planting': 'زراعة/بذر',
  'pruning': 'تقليم',
  'harvest': 'حصاد',
};

String isoDay(DateTime d) {
  final l = d.toLocal();
  return '${l.year.toString().padLeft(4, '0')}-'
      '${l.month.toString().padLeft(2, '0')}-'
      '${l.day.toString().padLeft(2, '0')}';
}

/// يفتح الورقة ويُعيد true إن حُفظ النشاط.
Future<bool> showActivityFormSheet(
  BuildContext context, {
  required String fieldId,
  required FieldsApi api,
}) async =>
    await showAppBottomSheet<bool>(
      context,
      builder: (_) => ActivityFormSheet(fieldId: fieldId, api: api),
    ) ??
    false;

class ActivityFormSheet extends StatefulWidget {
  const ActivityFormSheet({
    super.key,
    required this.fieldId,
    required this.api,
    this.now,
  });

  final String fieldId;
  final FieldsApi api;

  /// «اليوم» قابل للحقن في الاختبار.
  final DateTime Function()? now;

  @override
  State<ActivityFormSheet> createState() => _ActivityFormSheetState();
}

class _ActivityFormSheetState extends State<ActivityFormSheet> {
  final _title = TextEditingController();
  final _notes = TextEditingController();
  final IdempotencyKey _key = IdempotencyKey.generate();
  String _type = 'irrigation';
  late DateTime _performedOn = (widget.now ?? DateTime.now)();
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _title.dispose();
    _notes.dispose();
    super.dispose();
  }

  Future<void> _pickDate() async {
    final now = (widget.now ?? DateTime.now)();
    final d = await showDatePicker(
      context: context,
      initialDate: _performedOn,
      firstDate: DateTime(now.year - 2),
      lastDate: now,
    );
    if (d != null && mounted) setState(() => _performedOn = d);
  }

  Future<void> _save() async {
    if (_saving) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await widget.api.createFieldActivity(
        widget.fieldId,
        activityType: _type,
        titleAr: _title.text.trim().isEmpty
            ? kLoggableActivityTypes[_type]
            : _title.text.trim(),
        performedOn: isoDay(_performedOn),
        notes: _notes.text,
        idempotencyKey: _key,
      );
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _saving = false;
        _error = ApiException.from(e).messageAr;
      });
    }
  }

  @override
  Widget build(BuildContext context) => AppSheet(
    title: 'تسجيل نشاط',
    submitLabel: 'حفظ في السجلّ',
    submitting: _saving,
    onSubmit: _save,
    errorText: _error,
    children: [
      AppDropdown<String>(
        label: 'نوع النشاط',
        items: kLoggableActivityTypes,
        value: _type,
        onChanged: (v) => setState(() => _type = v ?? _type),
      ),
      AppTextField(
        key: const ValueKey('activity_title'),
        label: 'وصف مختصر (اختياريّ)',
        controller: _title,
      ),
      AppTextField(
        label: 'ملاحظات (اختياريّ)',
        controller: _notes,
        maxLines: 2,
      ),
      const SizedBox(height: SahoolSpacing.md),
      SecondaryButton(
        icon: Icons.calendar_today_outlined,
        label: 'تاريخ التنفيذ: ${fmtDate(_performedOn)}',
        onPressed: _pickDate,
      ),
    ],
  );
}
