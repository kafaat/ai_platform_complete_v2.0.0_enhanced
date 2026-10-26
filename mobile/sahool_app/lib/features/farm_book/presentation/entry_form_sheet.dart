// SAHOOL — features/farm_book/presentation/entry_form_sheet.dart
// نموذج قيد جديد: نوع (مصروف/إيراد/سداد دين) ← دفع (نقدي/آجل) ← تصنيف بلمسة ←
// مبلغ يقبل ٠-٩ و«٫» ← تاريخ ← طرف (لازم للآجل) ← حقل اختياريّ ← ملاحظة.
// مفتاح منع التكرار يُولَّد مرّة عند فتح الورقة ويُعاد في كلّ ضغطة «حفظ».
import 'package:flutter/material.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

import '../data/farm_book_models.dart';
import 'farm_book_cubit.dart';
import 'farm_book_parties_tab.dart';
import 'farm_book_state.dart';
import 'farm_book_text.dart';

class EntryFormSheet extends StatefulWidget {
  const EntryFormSheet({super.key, required this.cubit});
  final FarmBookCubit cubit;

  @override
  State<EntryFormSheet> createState() => _EntryFormSheetState();
}

class _EntryFormSheetState extends State<EntryFormSheet> {
  final IdempotencyKey _key = IdempotencyKey.generate();
  final _form = GlobalKey<FormState>();
  final _amount = TextEditingController();
  final _notes = TextEditingController();

  String _type = 'expense';
  String _method = 'cash';
  String _category = 'other_expense';
  late String _date = widget.cubit.today;
  String? _partyId;
  String? _fieldId;
  FarmBookEntry? _settles;

  Section<List<FarmBookEntry>>? _openCredits;
  bool _submitting = false;
  String? _error;

  FarmBookCubit get _cubit => widget.cubit;

  @override
  void dispose() {
    _amount.dispose();
    _notes.dispose();
    super.dispose();
  }

  void _setType(String type) {
    setState(() {
      _type = type;
      _error = null;
      if (type == 'expense' && !kExpenseCategories.containsKey(_category)) {
        _category = 'other_expense';
      } else if (type == 'income' &&
          !kIncomeCategories.containsKey(_category)) {
        _category = 'other_income';
      }
    });
    if (type == 'payment' && _openCredits == null) _loadOpenCredits();
  }

  Future<void> _loadOpenCredits() async {
    setState(() => _openCredits = const SectionLoading());
    try {
      final list = await _cubit.openCreditEntries();
      if (mounted) setState(() => _openCredits = SectionLoaded(list));
    } on Object catch (e) {
      if (mounted) {
        setState(() => _openCredits = SectionFailed(ApiException.from(e)));
      }
    }
  }

  Future<void> _pickDate() async {
    final now = DateTime.parse(_cubit.today);
    final picked = await showDatePicker(
      context: context,
      initialDate: DateTime.tryParse(_date) ?? now,
      firstDate: DateTime(2000),
      lastDate: now,
      helpText: 'تاريخ الحركة',
    );
    if (picked != null && mounted) setState(() => _date = isoDay(picked));
  }

  Future<void> _newParty() async {
    final party = await openPartySheet(context, _cubit);
    if (party != null && mounted) setState(() => _partyId = party.partyId);
  }

  Future<void> _submit() async {
    if (_submitting) return;
    if (!(_form.currentState?.validate() ?? false)) return;
    final amount = normalizeAmount(_amount.text);
    if (amount == null) return; // validateAmount منع ذلك أصلاً
    setState(() {
      _submitting = true;
      _error = null;
    });
    final outcome = await _cubit.submitEntry(
      FarmBookEntryDraft(
        entryType: _type,
        paymentMethod: _type == 'payment' ? 'cash' : _method,
        category: _type == 'payment' ? kPaymentCategory : _category,
        amount: amount,
        occurredOn: _date,
        fieldId: _fieldId,
        partyId: _partyId,
        settles: _type == 'payment' ? _settles : null,
        description: _notes.text,
      ),
      _key,
    );
    if (!mounted) return;
    if (outcome is WriteFailed) {
      setState(() {
        _submitting = false;
        _error = outcome.messageAr;
      });
      return;
    }
    Navigator.of(context).pop(outcome);
  }

  @override
  Widget build(BuildContext context) {
    final isPayment = _type == 'payment';
    final farm = _cubit.state.farm;
    final unit = currencyUnitAr(
      isPayment && _settles != null ? _settles!.currency : farm?.currency,
    );
    return Form(
      key: _form,
      child: AppSheet(
        title: 'قيد جديد',
        submitLabel: 'حفظ القيد',
        submitting: _submitting,
        errorText: _error,
        onSubmit: _submit,
        children: [
          const SizedBox(height: SahoolSpacing.md),
          SegmentedButton<String>(
            segments: const [
              ButtonSegment(value: 'expense', label: Text('مصروف')),
              ButtonSegment(value: 'income', label: Text('إيراد')),
              ButtonSegment(value: 'payment', label: Text('سداد دين')),
            ],
            selected: {_type},
            onSelectionChanged: (s) => _setType(s.first),
          ),
          if (!isPayment) ...[
            const SizedBox(height: SahoolSpacing.md),
            SegmentedButton<String>(
              segments: const [
                ButtonSegment(value: 'cash', label: Text('نقدي')),
                ButtonSegment(value: 'credit', label: Text('آجل')),
              ],
              selected: {_method},
              onSelectionChanged: (s) => setState(() => _method = s.first),
            ),
            const SizedBox(height: SahoolSpacing.md),
            Text('التصنيف', style: context.textStyles.labelLarge),
            const SizedBox(height: SahoolSpacing.xs),
            Wrap(
              spacing: SahoolSpacing.sm,
              runSpacing: SahoolSpacing.xs,
              children: [
                for (final c
                    in (_type == 'income'
                            ? kIncomeCategories
                            : kExpenseCategories)
                        .entries)
                  ChoiceChip(
                    label: Text(c.value),
                    selected: _category == c.key,
                    onSelected: (_) => setState(() => _category = c.key),
                  ),
              ],
            ),
          ],
          FarmBookAmountField(controller: _amount, unit: unit),
          Padding(
            padding: const EdgeInsets.only(top: SahoolSpacing.md),
            child: OutlinedButton.icon(
              style: OutlinedButton.styleFrom(
                minimumSize: const Size.fromHeight(SahoolSizes.minTouchTarget),
              ),
              onPressed: _pickDate,
              icon: const Icon(Icons.event_outlined),
              label: Text('التاريخ: ${fmtIsoDate(_date)}'),
            ),
          ),
          if (isPayment) _settleSelector(context) else _partySelector(context),
          if (_cubit.state.fieldOptions.isNotEmpty)
            AppDropdown<String?>(
              label: 'الحقل (اختياريّ)',
              items: {
                null: 'المزرعة كلّها',
                for (final f in _cubit.state.fieldOptions) f.id: f.name,
              },
              value: _fieldId,
              onChanged: (v) => setState(() => _fieldId = v),
            ),
          AppTextField(
            label: 'ملاحظة (اختياريّ)',
            controller: _notes,
            maxLines: 2,
            validator: (v) =>
                (v?.length ?? 0) > 2000 ? 'الملاحظة أطول من المسموح' : null,
          ),
        ],
      ),
    );
  }

  Widget _partySelector(BuildContext context) {
    final parties = _cubit.state.partyList;
    final credit = _method == 'credit';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        AppDropdown<String?>(
          key: ValueKey('party:$_partyId:${parties.length}'),
          label: credit ? 'المورد أو العميل (لازم للآجل)' : 'المورد أو العميل',
          items: {
            null: 'بدون طرف',
            for (final p in parties)
              p.partyId: '${p.name} — ${partyTypeLabel(p.partyType)}',
          },
          value: _partyId,
          onChanged: (v) => setState(() => _partyId = v),
          validator: (v) =>
              credit && v == null ? 'الآجل يحتاج تحديد المورد أو العميل' : null,
        ),
        if (_cubit.access.canWrite)
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: TextButton.icon(
              style: TextButton.styleFrom(
                minimumSize: const Size(0, SahoolSizes.minTouchTarget),
              ),
              onPressed: _newParty,
              icon: const Icon(Icons.person_add_alt_1_outlined),
              label: const Text('طرف جديد'),
            ),
          ),
      ],
    );
  }

  Widget _settleSelector(BuildContext context) {
    final s = _openCredits;
    return switch (s) {
      null || SectionLoading() || SectionNotAllowed() => const Padding(
        padding: EdgeInsets.all(SahoolSpacing.md),
        child: Center(child: CircularProgressIndicator()),
      ),
      SectionFailed(:final error) => Padding(
        padding: const EdgeInsets.only(top: SahoolSpacing.md),
        child: Row(
          children: [
            Expanded(
              child: Text(
                farmBookErrorMessage(error),
                style: context.textStyles.bodyMedium?.copyWith(
                  color: context.tokens.danger,
                ),
              ),
            ),
            AppIconButton(
              icon: Icons.refresh_rounded,
              tooltip: 'إعادة المحاولة',
              onPressed: _loadOpenCredits,
            ),
          ],
        ),
      ),
      SectionLoaded(:final data) when data.isEmpty => Padding(
        padding: const EdgeInsets.only(top: SahoolSpacing.md),
        child: Text(
          'لا قيود آجلة مفتوحة لهذه المزرعة.',
          style: context.textStyles.bodyMedium,
        ),
      ),
      SectionLoaded(:final data) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          AppDropdown<String>(
            label: 'القيد الآجل المراد سداده',
            items: {
              for (final e in data)
                e.entryId:
                    '${fmtIsoDate(e.occurredOn)} — '
                    '${e.partyName ?? 'طرف'} — '
                    '${fmtMoney(e.amount, e.currency)}',
            },
            value: _settles?.entryId,
            onChanged: (id) => setState(() {
              _settles = data.where((e) => e.entryId == id).firstOrNull;
              _partyId = _settles?.partyId;
            }),
            validator: (v) => v == null ? 'اختر القيد الآجل' : null,
          ),
          Padding(
            padding: const EdgeInsets.only(top: SahoolSpacing.xs),
            child: Text(
              'المبلغ المعروض أصل الدين؛ المتبقّي يتحقّق منه الخادم.',
              style: context.textStyles.bodySmall?.copyWith(
                color: context.tokens.muted,
              ),
            ),
          ),
        ],
      ),
    };
  }
}

/// حقل المبلغ: يحوّل ٠-٩ و«٫» أثناء الكتابة ويتحقّق بـ[validateAmount].
class FarmBookAmountField extends StatelessWidget {
  const FarmBookAmountField({
    super.key,
    required this.controller,
    required this.unit,
  });
  final TextEditingController controller;
  final String unit;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: SahoolSpacing.md),
    child: TextFormField(
      key: const ValueKey('farm_book_amount'),
      controller: controller,
      validator: validateAmount,
      keyboardType: const TextInputType.numberWithOptions(decimal: true),
      inputFormatters: const [LocalizedDigitsFormatter()],
      textInputAction: TextInputAction.done,
      decoration: InputDecoration(labelText: 'المبلغ', suffixText: unit),
    ),
  );
}
