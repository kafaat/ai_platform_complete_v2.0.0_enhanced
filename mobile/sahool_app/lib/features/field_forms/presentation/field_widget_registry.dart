/// سجلّ مغلق لبنّاءات widgets للأنواع الثمانية فقط (GAP-FIELD-FORMS-01 §15).
///
/// الأسماء هنا تفاصيل عرض داخليّة — لا ترد أبدًا في العقد الخادميّ؛
/// العقد يحمل field_type/presentation_hint فقط، والسجلّ يترجم النوع إلى بنّاء.
library;

import 'package:flutter/material.dart';

import '../contract/form_schema.dart';

/// سياق تمرير القيمة من الـrenderer إلى بنّاء الحقل.
typedef FieldChanged = void Function(Object? value);

typedef FieldWidgetBuilder = Widget Function(
  BuildContext context,
  FormFieldDef def,
  Object? value,
  String? errorText,
  FieldChanged onChanged,
);

/// مُلتقط صور قابل للحقن (الافتراضيّ image_picker في الشاشة) —
/// يعيد مرجع ملفّ (path) لا Base64.
typedef PhotoPicker = Future<String?> Function();

/// السجلّ المغلق: نوع من الثمانية ← بنّاء. لا امتداد وقت التشغيل.
class FieldWidgetRegistry {
  final PhotoPicker? photoPicker;

  const FieldWidgetRegistry({this.photoPicker});

  /// يعيد البنّاء أو null لنوع خارج السجلّ (لا يحدث — contract يرفض قبلها).
  /// سجلّ مغلق: switch شامل على الأنواع الثمانية فقط.
  FieldWidgetBuilder? builderFor(FormFieldType type) {
    switch (type) {
      case FormFieldType.text:
        return _buildText;
      case FormFieldType.number:
        return _buildNumber;
      case FormFieldType.integer:
        return _buildInteger;
      case FormFieldType.select:
        return _buildSelect;
      case FormFieldType.multiSelect:
        return _buildMultiSelect;
      case FormFieldType.date:
        return _buildDate;
      case FormFieldType.gps:
        return _buildGps;
      case FormFieldType.photo:
        return _buildPhoto;
    }
  }

  Widget _buildText(BuildContext context, FormFieldDef def, Object? value,
      String? errorText, FieldChanged onChanged) {
    return TextFormField(
      key: ValueKey('field_${def.key}'),
      initialValue: value is String ? value : '',
      decoration: InputDecoration(labelText: def.key, errorText: errorText),
      onChanged: (v) => onChanged(v.isEmpty ? null : v),
    );
  }

  Widget _buildNumber(BuildContext context, FormFieldDef def, Object? value,
      String? errorText, FieldChanged onChanged) {
    return TextFormField(
      key: ValueKey('field_${def.key}'),
      initialValue: value is num ? value.toString() : '',
      keyboardType: const TextInputType.numberWithOptions(decimal: true),
      decoration: InputDecoration(labelText: def.key, errorText: errorText),
      // نحوّل إدخال المستخدم إلى double؛ القيمة المخزَّنة JSON number فقط.
      // نصّ غير قابل للتحويل يبقى نصًّا فيرفضه التحقّق (لا coercion صامت).
      onChanged: (v) {
        if (v.isEmpty) return onChanged(null);
        final parsed = double.tryParse(v);
        onChanged(parsed ?? v);
      },
    );
  }

  Widget _buildInteger(BuildContext context, FormFieldDef def, Object? value,
      String? errorText, FieldChanged onChanged) {
    return TextFormField(
      key: ValueKey('field_${def.key}'),
      initialValue: value is int ? value.toString() : '',
      keyboardType: TextInputType.number,
      decoration: InputDecoration(labelText: def.key, errorText: errorText),
      // integer يبقى int: "3.5" لا يُقبل ولا يُقتطع؛ يبقى نصًّا فيرفضه التحقّق.
      onChanged: (v) {
        if (v.isEmpty) return onChanged(null);
        final parsed = int.tryParse(v);
        onChanged(parsed ?? v);
      },
    );
  }

  Widget _buildSelect(BuildContext context, FormFieldDef def, Object? value,
      String? errorText, FieldChanged onChanged) {
    final current = value is String && def.options.contains(value)
        ? value
        : null;
    return DropdownButtonFormField<String>(
      key: ValueKey('field_${def.key}'),
      value: current,
      decoration: InputDecoration(labelText: def.key, errorText: errorText),
      items: def.options
          .map((o) => DropdownMenuItem<String>(value: o, child: Text(o)))
          .toList(),
      onChanged: (v) => onChanged(v),
    );
  }

  Widget _buildMultiSelect(BuildContext context, FormFieldDef def,
      Object? value, String? errorText, FieldChanged onChanged) {
    final selected = <String>{
      if (value is List)
        ...value.whereType<String>().where(def.options.contains),
    };
    return Column(
      key: ValueKey('field_${def.key}'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(def.key, style: Theme.of(context).textTheme.bodyLarge),
        if (errorText != null)
          Text(errorText,
              style: TextStyle(color: Theme.of(context).colorScheme.error)),
        for (final option in def.options)
          CheckboxListTile(
            key: ValueKey('field_${def.key}_opt_$option'),
            title: Text(option),
            value: selected.contains(option),
            onChanged: (checked) {
              final next = <String>[...selected];
              if (checked == true) {
                next.add(option);
              } else {
                next.remove(option);
              }
              // الترتيب حسب ترتيب options للاستقرار.
              next.sort((a, b) => def.options
                  .indexOf(a)
                  .compareTo(def.options.indexOf(b)));
              onChanged(next.isEmpty ? null : next);
            },
          ),
      ],
    );
  }

  Widget _buildDate(BuildContext context, FormFieldDef def, Object? value,
      String? errorText, FieldChanged onChanged) {
    final controller = TextEditingController(
        text: value is String ? value : '');
    return TextFormField(
      key: ValueKey('field_${def.key}'),
      controller: controller,
      readOnly: true,
      decoration: InputDecoration(
        labelText: def.key,
        hintText: 'YYYY-MM-DD',
        errorText: errorText,
        suffixIcon: const Icon(Icons.calendar_today),
      ),
      onTap: () async {
        final now = DateTime.now();
        final picked = await showDatePicker(
          context: context,
          initialDate: now,
          firstDate: DateTime(now.year - 20),
          lastDate: DateTime(now.year + 20),
        );
        if (picked != null) {
          // التخزين String بصيغة YYYY-MM-DD فقط.
          final iso = picked.toIso8601String().substring(0, 10);
          controller.text = iso;
          onChanged(iso);
        }
      },
    );
  }

  Widget _buildGps(BuildContext context, FormFieldDef def, Object? value,
      String? errorText, FieldChanged onChanged) {
    return _GpsField(def: def, value: value, errorText: errorText,
        onChanged: onChanged);
  }

  Widget _buildPhoto(BuildContext context, FormFieldDef def, Object? value,
      String? errorText, FieldChanged onChanged) {
    final reference = value is String && value.isNotEmpty ? value : null;
    return Column(
      key: ValueKey('field_${def.key}'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        OutlinedButton.icon(
          key: ValueKey('field_${def.key}_pick'),
          icon: const Icon(Icons.photo_camera),
          label: Text(reference == null ? 'التقاط صورة' : 'صورة مرفقة'),
          onPressed: photoPicker == null
              ? null
              : () async {
                  final path = await photoPicker!();
                  if (path != null && path.isNotEmpty) {
                    // مرجع ملفّ فقط — لا Base64 داخل answers.
                    onChanged(path);
                  }
                },
        ),
        if (reference != null)
          Text(reference,
              key: ValueKey('field_${def.key}_ref'),
              style: Theme.of(context).textTheme.bodySmall),
        if (errorText != null)
          Text(errorText,
              style: TextStyle(color: Theme.of(context).colorScheme.error)),
      ],
    );
  }
}

/// حقل gps بحالة داخليّة: lat/lng مستقلّان ولا يضيعان عند إعادة البناء.
class _GpsField extends StatefulWidget {
  final FormFieldDef def;
  final Object? value;
  final String? errorText;
  final FieldChanged onChanged;

  const _GpsField({required this.def, this.value, this.errorText,
      required this.onChanged});

  @override
  State<_GpsField> createState() => _GpsFieldState();
}

class _GpsFieldState extends State<_GpsField> {
  double? _lat;
  double? _lng;

  @override
  void initState() {
    super.initState();
    final v = widget.value;
    if (v is Map) {
      if (v['lat'] is num) _lat = (v['lat'] as num).toDouble();
      if (v['lng'] is num) _lng = (v['lng'] as num).toDouble();
    }
  }

  void _emit() {
    final lat = _lat;
    final lng = _lng;
    if (lat != null && lng != null) {
      widget.onChanged({'lat': lat, 'lng': lng});
    } else {
      widget.onChanged(null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final def = widget.def;
    return Column(
      key: ValueKey('field_${def.key}'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(def.key, style: Theme.of(context).textTheme.bodyLarge),
        if (widget.errorText != null)
          Text(widget.errorText!,
              style: TextStyle(color: Theme.of(context).colorScheme.error)),
        TextFormField(
          key: ValueKey('field_${def.key}_lat'),
          initialValue: _lat?.toString() ?? '',
          keyboardType: const TextInputType.numberWithOptions(
              decimal: true, signed: true),
          decoration: const InputDecoration(labelText: 'lat'),
          onChanged: (v) {
            _lat = double.tryParse(v);
            _emit();
          },
        ),
        TextFormField(
          key: ValueKey('field_${def.key}_lng'),
          initialValue: _lng?.toString() ?? '',
          keyboardType: const TextInputType.numberWithOptions(
              decimal: true, signed: true),
          decoration: const InputDecoration(labelText: 'lng'),
          onChanged: (v) {
            _lng = double.tryParse(v);
            _emit();
          },
        ),
      ],
    );
  }
}
