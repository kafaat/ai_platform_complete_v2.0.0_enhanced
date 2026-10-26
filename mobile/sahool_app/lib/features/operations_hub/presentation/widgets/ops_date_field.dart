// SAHOOL — features/operations_hub/presentation/widgets/ops_date_field.dart
// مشترك بين وحدات العمليّات — مرشّح للنقل إلى core/widgets.
// حقل تاريخ بمنتقٍ (لا كتابة YYYY-MM-DD يدويّاً): يعرض التاريخ بالعربيّة، ويُمسَح
// بزرّ واضح، وهدف لمسه ≥48dp.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

class OpsDateField extends StatelessWidget {
  const OpsDateField({
    super.key,
    required this.label,
    required this.value,
    required this.onChanged,
    required this.firstDate,
    required this.lastDate,
    this.errorText,
  });

  final String label;
  final DateTime? value;
  final ValueChanged<DateTime?> onChanged;
  final DateTime firstDate;
  final DateTime lastDate;
  final String? errorText;

  Future<void> _pick(BuildContext context) async {
    final now = DateTime.now();
    var initial = value ?? now;
    if (initial.isBefore(firstDate)) initial = firstDate;
    if (initial.isAfter(lastDate)) initial = lastDate;
    final picked = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: firstDate,
      lastDate: lastDate,
      helpText: label,
    );
    if (picked != null) onChanged(picked);
  }

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: SahoolSpacing.md),
    child: InkWell(
      onTap: () => _pick(context),
      borderRadius: SahoolRadius.smAll,
      child: InputDecorator(
        decoration: InputDecoration(
          labelText: label,
          errorText: errorText,
          suffixIcon: value == null
              ? const Icon(Icons.calendar_month_outlined)
              : AppIconButton(
                  icon: Icons.close_rounded,
                  tooltip: 'مسح $label',
                  onPressed: () => onChanged(null),
                ),
        ),
        child: Text(value == null ? 'اختر التاريخ' : fmtDate(value)),
      ),
    ),
  );
}
