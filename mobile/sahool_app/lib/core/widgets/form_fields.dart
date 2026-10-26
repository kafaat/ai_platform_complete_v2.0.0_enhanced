// SAHOOL — lib/core/widgets/form_fields.dart
// أغلفة حقول النموذج المتّسقة مع السمة. حقل الأرقام يقبل الأرقام العربيّة-الهنديّة
// و«٫» ويحوّلها أثناء الكتابة (LocalizedDigitsFormatter)، فيُحلَّل بـ
// parseLocalizedNum دون فقدان صامت. التحقّق يُعرَض سطريّاً تحت الحقل (errorText)
// لا في SnackBar يختفي خلف الورقة السفليّة.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';

class AppTextField extends StatelessWidget {
  const AppTextField({
    super.key,
    required this.label,
    this.controller,
    this.hint,
    this.helper,
    this.errorText,
    this.validator,
    this.keyboardType,
    this.inputFormatters,
    this.maxLines = 1,
    this.obscure = false,
    this.enabled = true,
    this.prefixIcon,
    this.onChanged,
    this.textInputAction,
    this.autofillHints,
  });

  final String label;
  final TextEditingController? controller;
  final String? hint;
  final String? helper;
  final String? errorText;
  final FormFieldValidator<String>? validator;
  final TextInputType? keyboardType;
  final List<TextInputFormatter>? inputFormatters;
  final int maxLines;
  final bool obscure;
  final bool enabled;
  final IconData? prefixIcon;
  final ValueChanged<String>? onChanged;
  final TextInputAction? textInputAction;
  final Iterable<String>? autofillHints;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(top: SahoolSpacing.md),
        child: TextFormField(
          controller: controller,
          validator: validator,
          keyboardType: keyboardType,
          inputFormatters: inputFormatters,
          maxLines: obscure ? 1 : maxLines,
          obscureText: obscure,
          enabled: enabled,
          onChanged: onChanged,
          textInputAction: textInputAction,
          autofillHints: autofillHints,
          decoration: InputDecoration(
            labelText: label,
            hintText: hint,
            helperText: helper,
            errorText: errorText,
            prefixIcon: prefixIcon != null ? Icon(prefixIcon) : null,
          ),
        ),
      );
}

/// حقل رقم: لوحة أرقام + تحويل الأرقام العربيّة + تحقّق النطاق اختياريّاً.
/// اقرأ القيمة بـ`parseLocalizedNum(controller.text)`.
class AppNumberField extends StatelessWidget {
  const AppNumberField({
    super.key,
    required this.label,
    required this.controller,
    this.unit,
    this.decimal = true,
    this.required = false,
    this.min,
    this.max,
    this.helper,
  });

  final String label;
  final TextEditingController controller;
  final String? unit;
  final bool decimal;
  final bool required;
  final num? min;
  final num? max;
  final String? helper;

  String? _validate(String? raw) {
    final text = raw?.trim() ?? '';
    if (text.isEmpty) return required ? 'هذا الحقل مطلوب' : null;
    final v = parseLocalizedNum(text);
    if (v == null) return 'أدخل رقماً صحيحاً';
    if (!decimal && v != v.roundToDouble()) return 'أدخل عدداً صحيحاً';
    if (min != null && v < min!) return 'القيمة أقلّ من ${fmtNumber(min, decimals: 2)}';
    if (max != null && v > max!) return 'القيمة أكبر من ${fmtNumber(max, decimals: 2)}';
    return null;
  }

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(top: SahoolSpacing.md),
        child: TextFormField(
          controller: controller,
          validator: _validate,
          autovalidateMode: AutovalidateMode.onUserInteraction,
          keyboardType: TextInputType.numberWithOptions(decimal: decimal),
          inputFormatters: [
            LocalizedDigitsFormatter(digitsOnly: !decimal),
          ],
          decoration: InputDecoration(
            labelText: label,
            helperText: helper,
            suffixText: unit,
          ),
        ),
      );
}

/// قائمة منسدلة مُنمَّطة. [items]: القيمة ← التسمية العربيّة.
class AppDropdown<T> extends StatelessWidget {
  const AppDropdown({
    super.key,
    required this.label,
    required this.items,
    required this.value,
    required this.onChanged,
    this.validator,
  });

  final String label;
  final Map<T, String> items;
  final T? value;
  final ValueChanged<T?>? onChanged;
  final FormFieldValidator<T>? validator;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(top: SahoolSpacing.md),
        child: DropdownButtonFormField<T>(
          initialValue: value,
          isExpanded: true,
          validator: validator,
          decoration: InputDecoration(labelText: label),
          items: [
            for (final e in items.entries)
              DropdownMenuItem<T>(value: e.key, child: Text(e.value)),
          ],
          onChanged: onChanged,
        ),
      );
}
