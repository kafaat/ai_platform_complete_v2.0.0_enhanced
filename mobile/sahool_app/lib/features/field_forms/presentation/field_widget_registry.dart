/// سجلّ مغلق لبنّاءات widgets للأنواع الثمانية فقط (GAP-FIELD-FORMS-01 §15).
///
/// الأسماء هنا تفاصيل عرض داخليّة — لا ترد أبدًا في العقد الخادميّ؛
/// العقد يحمل field_type/presentation_hint فقط، والسجلّ يترجم النوع إلى بنّاء.
library;

import 'package:flutter/material.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';

import '../contract/form_schema.dart';

/// سياق تمرير القيمة من الـrenderer إلى بنّاء الحقل.
typedef FieldChanged = void Function(Object? value);

typedef FieldWidgetBuilder =
    Widget Function(
      BuildContext context,
      FormFieldDef def,
      Object? value,
      String? errorText,
      FieldChanged onChanged,
    );

/// مُلتقط صور قابل للحقن (الافتراضيّ image_picker في الشاشة) —
/// يعيد مرجع ملفّ (path) لا Base64.
typedef PhotoPicker = Future<String?> Function();

/// قارئ موقع الجهاز (الافتراضيّ geolocator في الشاشة). null ⇒ تعذّر القراءة.
typedef LocationPicker = Future<({double lat, double lng})?> Function();

/// التسمية المعروضة: «*» للحقل الإلزاميّ (لا يُكتفى باللون).
String _label(FormFieldDef def) =>
    def.required ? '${def.displayLabel} *' : def.displayLabel;

/// السجلّ المغلق: نوع من الثمانية ← بنّاء. لا امتداد وقت التشغيل.
class FieldWidgetRegistry {
  final PhotoPicker? photoPicker;
  final LocationPicker? locationPicker;

  const FieldWidgetRegistry({this.photoPicker, this.locationPicker});

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

  Widget _buildText(
    BuildContext context,
    FormFieldDef def,
    Object? value,
    String? errorText,
    FieldChanged onChanged,
  ) {
    return TextFormField(
      key: ValueKey('field_${def.key}'),
      initialValue: value is String ? value : '',
      maxLines: null,
      decoration: InputDecoration(labelText: _label(def), errorText: errorText),
      onChanged: (v) => onChanged(v.isEmpty ? null : v),
    );
  }

  Widget _buildNumber(
    BuildContext context,
    FormFieldDef def,
    Object? value,
    String? errorText,
    FieldChanged onChanged,
  ) {
    return TextFormField(
      key: ValueKey('field_${def.key}'),
      initialValue: value is num ? value.toString() : '',
      keyboardType: const TextInputType.numberWithOptions(decimal: true),
      decoration: InputDecoration(labelText: _label(def), errorText: errorText),
      // نحوّل إدخال المستخدم إلى double؛ القيمة المخزَّنة JSON number فقط.
      // الأرقام العربيّة-الهنديّة (٢٫٥) تُقرأ كأرقام — لوحة المفاتيح العربيّة
      // تكتبها افتراضيّاً. نصّ غير قابل للتحويل يبقى نصًّا فيرفضه التحقّق.
      onChanged: (v) {
        if (v.trim().isEmpty) return onChanged(null);
        final parsed = parseLocalizedNum(v);
        onChanged(parsed ?? v);
      },
    );
  }

  Widget _buildInteger(
    BuildContext context,
    FormFieldDef def,
    Object? value,
    String? errorText,
    FieldChanged onChanged,
  ) {
    return TextFormField(
      key: ValueKey('field_${def.key}'),
      initialValue: value is int ? value.toString() : '',
      keyboardType: TextInputType.number,
      decoration: InputDecoration(labelText: _label(def), errorText: errorText),
      // integer يبقى int: "3.5" لا يُقبل ولا يُقتطع؛ يبقى نصًّا فيرفضه التحقّق.
      onChanged: (v) {
        if (v.trim().isEmpty) return onChanged(null);
        final parsed = parseLocalizedInt(v);
        onChanged(parsed ?? v);
      },
    );
  }

  Widget _buildSelect(
    BuildContext context,
    FormFieldDef def,
    Object? value,
    String? errorText,
    FieldChanged onChanged,
  ) {
    final current = value is String && def.options.contains(value)
        ? value
        : null;
    return DropdownButtonFormField<String>(
      key: ValueKey('field_${def.key}'),
      initialValue: current,
      isExpanded: true,
      decoration: InputDecoration(labelText: _label(def), errorText: errorText),
      items: def.options
          .map(
            (o) => DropdownMenuItem<String>(
              value: o,
              child: Text(def.optionLabel(o)),
            ),
          )
          .toList(),
      onChanged: (v) => onChanged(v),
    );
  }

  Widget _buildMultiSelect(
    BuildContext context,
    FormFieldDef def,
    Object? value,
    String? errorText,
    FieldChanged onChanged,
  ) {
    final selected = <String>{
      if (value is List)
        ...value.whereType<String>().where(def.options.contains),
    };
    return Column(
      key: ValueKey('field_${def.key}'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(_label(def), style: context.textStyles.bodyLarge),
        if (errorText != null)
          Text(
            errorText,
            style: TextStyle(color: Theme.of(context).colorScheme.error),
          ),
        for (final option in def.options)
          CheckboxListTile(
            key: ValueKey('field_${def.key}_opt_$option'),
            title: Text(def.optionLabel(option)),
            value: selected.contains(option),
            onChanged: (checked) {
              final next = <String>[...selected];
              if (checked == true) {
                next.add(option);
              } else {
                next.remove(option);
              }
              // الترتيب حسب ترتيب options للاستقرار.
              next.sort(
                (a, b) =>
                    def.options.indexOf(a).compareTo(def.options.indexOf(b)),
              );
              onChanged(next.isEmpty ? null : next);
            },
          ),
      ],
    );
  }

  Widget _buildDate(
    BuildContext context,
    FormFieldDef def,
    Object? value,
    String? errorText,
    FieldChanged onChanged,
  ) {
    return _DateField(
      def: def,
      value: value,
      errorText: errorText,
      onChanged: onChanged,
    );
  }

  Widget _buildGps(
    BuildContext context,
    FormFieldDef def,
    Object? value,
    String? errorText,
    FieldChanged onChanged,
  ) {
    return _GpsField(
      def: def,
      value: value,
      errorText: errorText,
      onChanged: onChanged,
      locationPicker: locationPicker,
    );
  }

  Widget _buildPhoto(
    BuildContext context,
    FormFieldDef def,
    Object? value,
    String? errorText,
    FieldChanged onChanged,
  ) {
    final reference = value is String && value.isNotEmpty ? value : null;
    final t = context.tokens;
    return Column(
      key: ValueKey('field_${def.key}'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(_label(def), style: context.textStyles.bodyLarge),
        const SizedBox(height: SahoolSpacing.sm),
        SizedBox(
          height: SahoolSizes.minTouchTarget,
          child: OutlinedButton.icon(
            key: ValueKey('field_${def.key}_pick'),
            icon: const Icon(Icons.photo_camera_outlined),
            label: Text(
              reference == null ? 'التقاط صورة' : 'استبدال الصورة المرفقة',
            ),
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
        ),
        if (reference != null)
          Text(
            'صورة محفوظة على الجهاز: ${reference.split('/').last}',
            key: ValueKey('field_${def.key}_ref'),
            style: context.textStyles.bodySmall,
          ),
        Text(
          'رفع الصور غير متاح بعد في الخادم: يُرسل مرجع الصورة على الجهاز فقط.',
          style: context.textStyles.bodySmall?.copyWith(color: t.muted),
        ),
        if (errorText != null)
          Text(
            errorText,
            style: TextStyle(color: Theme.of(context).colorScheme.error),
          ),
      ],
    );
  }
}

/// حقل تاريخ: المتحكّم يعيش في الحالة ويُتلَف معها (كان يُنشأ في كلّ build ولا
/// يُتلَف). القيمة المخزَّنة String بصيغة YYYY-MM-DD فقط.
class _DateField extends StatefulWidget {
  const _DateField({
    required this.def,
    required this.value,
    required this.errorText,
    required this.onChanged,
  });

  final FormFieldDef def;
  final Object? value;
  final String? errorText;
  final FieldChanged onChanged;

  @override
  State<_DateField> createState() => _DateFieldState();
}

class _DateFieldState extends State<_DateField> {
  late final TextEditingController _controller = TextEditingController(
    text: widget.value is String ? widget.value! as String : '',
  );

  @override
  void didUpdateWidget(covariant _DateField oldWidget) {
    super.didUpdateWidget(oldWidget);
    final next = widget.value is String ? widget.value! as String : '';
    if (next != _controller.text) _controller.text = next;
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _pick() async {
    final now = DateTime.now();
    final current = DateTime.tryParse(_controller.text);
    final picked = await showDatePicker(
      context: context,
      initialDate: current ?? now,
      firstDate: DateTime(now.year - 20),
      lastDate: DateTime(now.year + 20),
    );
    if (picked != null && mounted) {
      final iso = picked.toIso8601String().substring(0, 10);
      _controller.text = iso;
      widget.onChanged(iso);
    }
  }

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      key: ValueKey('field_${widget.def.key}'),
      controller: _controller,
      readOnly: true,
      decoration: InputDecoration(
        labelText: _label(widget.def),
        hintText: 'اختر التاريخ',
        errorText: widget.errorText,
        suffixIcon: const Icon(Icons.calendar_today_outlined),
      ),
      onTap: _pick,
    );
  }
}

/// حقل gps بحالة داخليّة: lat/lng مستقلّان ولا يضيعان عند إعادة البناء.
/// «موقعي الحاليّ» يملأ الإحداثيّين بلمسة؛ الإدخال اليدويّ يبقى متاحاً ويقبل
/// الأرقام العربيّة-الهنديّة.
class _GpsField extends StatefulWidget {
  final FormFieldDef def;
  final Object? value;
  final String? errorText;
  final FieldChanged onChanged;
  final LocationPicker? locationPicker;

  const _GpsField({
    required this.def,
    this.value,
    this.errorText,
    required this.onChanged,
    this.locationPicker,
  });

  @override
  State<_GpsField> createState() => _GpsFieldState();
}

class _GpsFieldState extends State<_GpsField> {
  double? _lat;
  double? _lng;
  late final TextEditingController _latCtrl;
  late final TextEditingController _lngCtrl;
  bool _locating = false;
  String? _locateError;

  @override
  void initState() {
    super.initState();
    final v = widget.value;
    if (v is Map) {
      if (v['lat'] is num) _lat = (v['lat'] as num).toDouble();
      if (v['lng'] is num) _lng = (v['lng'] as num).toDouble();
    }
    _latCtrl = TextEditingController(text: _lat?.toString() ?? '');
    _lngCtrl = TextEditingController(text: _lng?.toString() ?? '');
  }

  @override
  void dispose() {
    _latCtrl.dispose();
    _lngCtrl.dispose();
    super.dispose();
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

  Future<void> _useCurrent() async {
    final picker = widget.locationPicker;
    if (picker == null || _locating) return;
    setState(() {
      _locating = true;
      _locateError = null;
    });
    ({double lat, double lng})? fix;
    try {
      fix = await picker();
    } catch (_) {
      fix = null;
    }
    if (!mounted) return;
    setState(() {
      _locating = false;
      if (fix == null) {
        _locateError =
            'تعذّر تحديد الموقع. فعّل الموقع أو أدخل الإحداثيّات يدويّاً.';
      } else {
        _lat = fix.lat;
        _lng = fix.lng;
        _latCtrl.text = fix.lat.toStringAsFixed(6);
        _lngCtrl.text = fix.lng.toStringAsFixed(6);
      }
    });
    if (fix != null) _emit();
  }

  @override
  Widget build(BuildContext context) {
    final def = widget.def;
    const coordKeyboard = TextInputType.numberWithOptions(
      decimal: true,
      signed: true,
    );
    return Column(
      key: ValueKey('field_${def.key}'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(_label(def), style: context.textStyles.bodyLarge),
        if (widget.errorText != null)
          Text(
            widget.errorText!,
            style: TextStyle(color: Theme.of(context).colorScheme.error),
          ),
        if (widget.locationPicker != null) ...[
          const SizedBox(height: SahoolSpacing.sm),
          SizedBox(
            height: SahoolSizes.minTouchTarget,
            child: OutlinedButton.icon(
              key: ValueKey('field_${def.key}_locate'),
              onPressed: _locating ? null : _useCurrent,
              icon: _locating
                  ? const SizedBox.square(
                      dimension: SahoolSizes.iconSm,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.my_location_outlined),
              label: Text(_locating ? 'جارٍ تحديد الموقع…' : 'موقعي الحاليّ'),
            ),
          ),
          if (_locateError != null)
            Text(
              _locateError!,
              style: TextStyle(color: context.tokens.warning),
            ),
        ],
        const SizedBox(height: SahoolSpacing.sm),
        TextFormField(
          key: ValueKey('field_${def.key}_lat'),
          controller: _latCtrl,
          keyboardType: coordKeyboard,
          textDirection: TextDirection.ltr,
          decoration: const InputDecoration(labelText: 'خطّ العرض'),
          onChanged: (v) {
            _lat = parseLocalizedNum(v);
            _emit();
          },
        ),
        const SizedBox(height: SahoolSpacing.sm),
        TextFormField(
          key: ValueKey('field_${def.key}_lng'),
          controller: _lngCtrl,
          keyboardType: coordKeyboard,
          textDirection: TextDirection.ltr,
          decoration: const InputDecoration(labelText: 'خطّ الطول'),
          onChanged: (v) {
            _lng = parseLocalizedNum(v);
            _emit();
          },
        ),
      ],
    );
  }
}
