// SAHOOL — features/devices/presentation/register_device_sheet.dart
// تسجيل جهاز في سجلّ المستأجر (device:manage — المالك/المدير). ربط الجهاز بحقل
// مهمّ: الخادم لا يوصل قراءة رطوبة التربة إلى أيّ قرار زراعيّ من جهاز بلا حقل
// (devices.py: device_not_linked_to_field)، فالورقة تقول ذلك. مفتاح منع تكرار واحد
// لعمر الورقة، وتحقّق وأخطاء الخادم داخلها لا في SnackBar تحتها.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/devices/data/devices_api.dart';
import 'package:sahool_app/features/devices/data/devices_models.dart';

import 'devices_cubit.dart';

const String kDeviceFixFields = 'راجع الحقول المعلَّمة باللون الأحمر.';

/// قيمة «بلا حقل» في القائمة المنسدلة.
const String _noField = '';

class RegisterDeviceSheet extends StatefulWidget {
  const RegisterDeviceSheet({super.key, required this.api, this.fields});

  final DevicesApi api;
  final FieldsLoader? fields;

  @override
  State<RegisterDeviceSheet> createState() => _RegisterDeviceSheetState();
}

class _RegisterDeviceSheetState extends State<RegisterDeviceSheet> {
  final _form = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _firmware = TextEditingController();
  final IdempotencyKey _key = IdempotencyKey.generate();
  String _type = 'soil_moisture';
  String _fieldId = _noField;
  Map<String, String>? _fieldNames;
  String? _fieldsError;
  bool _submitting = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadFields();
  }

  Future<void> _loadFields() async {
    try {
      final list = await Future.sync(widget.fields ?? defaultFieldsLoader());
      if (!mounted) return;
      setState(() => _fieldNames = fieldNamesOf(list));
    } catch (e) {
      if (!mounted) return;
      setState(() => _fieldsError = ApiException.from(e).messageAr);
    }
  }

  @override
  void dispose() {
    _name.dispose();
    _firmware.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_submitting) return;
    if (!(_form.currentState?.validate() ?? false)) {
      setState(() => _error = kDeviceFixFields);
      return;
    }
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      await widget.api.registerDevice({
        'name': _name.text.trim(),
        'type': _type,
        if (_fieldId != _noField) 'field_id': _fieldId,
        if (_firmware.text.trim().isNotEmpty)
          'firmware_version': _firmware.text.trim(),
      }, idempotencyKey: _key);
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _submitting = false;
        _error = ApiException.from(e).messageAr;
      });
    }
  }

  Widget _fieldPicker(BuildContext context) {
    final names = _fieldNames;
    if (names == null && _fieldsError == null) {
      return const Padding(
        padding: EdgeInsets.only(top: SahoolSpacing.md),
        child: LinearProgressIndicator(),
      );
    }
    if (names == null) {
      return Padding(
        padding: const EdgeInsets.only(top: SahoolSpacing.md),
        child: Text(
          'تعذّر تحميل الحقول: $_fieldsError\nيمكن التسجيل بلا حقل الآن.',
          style: context.textStyles.bodySmall?.copyWith(
            color: context.tokens.warning,
          ),
        ),
      );
    }
    return AppDropdown<String>(
      label: 'الحقل',
      items: {_noField: 'بلا حقل', ...names},
      value: _fieldId,
      onChanged: (v) => setState(() => _fieldId = v ?? _noField),
    );
  }

  @override
  Widget build(BuildContext context) {
    final unlinkedSoil = _type == 'soil_moisture' && _fieldId == _noField;
    return Form(
      key: _form,
      child: AppSheet(
        title: 'تسجيل جهاز',
        submitLabel: 'تسجيل الجهاز',
        submitting: _submitting,
        onSubmit: _submit,
        errorText: _error,
        children: [
          AppDropdown<String>(
            label: 'النوع',
            items: kDeviceTypes,
            value: _type,
            onChanged: (v) => setState(() => _type = v ?? 'other'),
          ),
          AppTextField(
            label: 'الاسم',
            hint: 'مثل: حسّاس رطوبة — الحقل الشماليّ',
            controller: _name,
            validator: (v) => (v ?? '').trim().isEmpty ? 'الاسم مطلوب' : null,
          ),
          _fieldPicker(context),
          if (unlinkedSoil)
            Padding(
              padding: const EdgeInsets.only(top: SahoolSpacing.sm),
              child: Text(
                'قراءات رطوبة التربة من جهاز بلا حقل لا تصل إلى توصيات الريّ.',
                style: context.textStyles.bodySmall?.copyWith(
                  color: context.tokens.warning,
                ),
              ),
            ),
          AppTextField(
            label: 'إصدار البرنامج الثابت (اختياري)',
            controller: _firmware,
          ),
        ],
      ),
    );
  }
}
