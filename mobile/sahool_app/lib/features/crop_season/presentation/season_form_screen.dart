// SAHOOL — features/crop_season/presentation/season_form_screen.dart
// إنشاء/تعديل موسم: المحصول من الفهرس (بلا كتابة)، الصنف، الريّ، تاريخ الزراعة،
// الحصاد المتوقّع، الإنتاجيّة المستهدفة، ملاحظات. التواريخ تُعرَض بأسماء الأشهر
// العربيّة (fmtDate) وتُرسَل «YYYY-MM-DD». الأخطاء سطريّة تحت الحقل.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

import '../data/crop_season_api.dart';
import '../data/season_models.dart';
import 'season_form_cubit.dart';
import 'season_form_logic.dart';

class SeasonFormScreen extends StatelessWidget {
  const SeasonFormScreen({
    super.key,
    required this.fieldId,
    this.original,
    this.catalog = const [],
    this.hasActiveSeason = false,
    this.api,
    this.today,
  });

  final String fieldId;
  final Season? original;
  final List<CropOption> catalog;

  /// إنشاء موسم جديد يُغلق الموسم النشط الحاليّ على الخادم — نحذّر قبله.
  final bool hasActiveSeason;
  final CropSeasonApi? api;

  /// قابل للحقن في الاختبارات.
  final DateTime? today;

  @override
  Widget build(BuildContext context) => BlocProvider(
    create: (_) => SeasonFormCubit(
      api ?? CropSeasonApi.instance,
      fieldId: fieldId,
      original: original,
    ),
    child: _SeasonForm(
      original: original,
      catalog: catalog,
      hasActiveSeason: hasActiveSeason,
      today: today,
    ),
  );
}

class _SeasonForm extends StatefulWidget {
  const _SeasonForm({
    required this.original,
    required this.catalog,
    required this.hasActiveSeason,
    this.today,
  });

  final Season? original;
  final List<CropOption> catalog;
  final bool hasActiveSeason;
  final DateTime? today;

  @override
  State<_SeasonForm> createState() => _SeasonFormState();
}

class _SeasonFormState extends State<_SeasonForm> {
  late final TextEditingController _cultivar;
  late final TextEditingController _cropText;
  late final TextEditingController _yield;
  late final TextEditingController _notes;
  String? _crop;
  String? _irrigation;
  DateTime? _sowing;
  DateTime? _end;

  bool get _isEdit => widget.original != null;
  bool get _useCatalog => widget.catalog.isNotEmpty;

  @override
  void initState() {
    super.initState();
    final o = widget.original;
    _crop = o?.primaryCrop;
    _cultivar = TextEditingController(text: o?.cultivar ?? '');
    _cropText = TextEditingController(text: o?.primaryCrop ?? '');
    _yield = TextEditingController(
      text: o?.targetYieldKgHa == null
          ? ''
          : fmtNumber(o!.targetYieldKgHa, decimals: 2).replaceAll(',', ''),
    );
    _notes = TextEditingController(text: o?.notesAr ?? '');
    _irrigation = o?.irrigationType;
    _sowing = o?.sowingDay;
    _end = o?.seasonEndDay;
  }

  @override
  void dispose() {
    _cultivar.dispose();
    _cropText.dispose();
    _yield.dispose();
    _notes.dispose();
    super.dispose();
  }

  SeasonFormInput _input() => SeasonFormInput(
    crop: _useCatalog ? _crop : _cropText.text,
    cultivar: _cultivar.text,
    irrigationType: _irrigation,
    sowingDate: _sowing,
    seasonEnd: _end,
    targetYieldText: _yield.text,
    notes: _notes.text,
  );

  Future<void> _submit() async {
    final cubit = context.read<SeasonFormCubit>();
    if (!_isEdit && widget.hasActiveSeason) {
      final ok = await showConfirmDialog(
        context,
        title: 'بدء موسم جديد',
        message:
            'يوجد موسم نشط لهذا الحقل. حفظ الموسم الجديد يُغلق الموسم '
            'النشط الحاليّ تلقائيّاً، والإغلاق نهائيّ.',
        confirmLabel: 'متابعة',
      );
      if (!ok || !mounted) return;
    }
    await cubit.submit(_input());
  }

  Future<void> _pickDate({required bool sowing}) async {
    final now = widget.today ?? DateTime.now();
    final current = sowing ? _sowing : _end;
    final picked = await showDatePicker(
      context: context,
      initialDate: current ?? (sowing ? now : (_sowing ?? now)),
      firstDate: DateTime(now.year - 5),
      lastDate: DateTime(now.year + 3, 12, 31),
      helpText: sowing ? 'تاريخ الزراعة' : 'الحصاد المتوقّع',
    );
    if (picked == null || !mounted) return;
    setState(() => sowing ? _sowing = picked : _end = picked);
  }

  @override
  Widget build(BuildContext context) {
    return BlocConsumer<SeasonFormCubit, SeasonFormState>(
      listener: (context, state) {
        if (state is SeasonFormSaved) Navigator.of(context).pop(state.season);
      },
      builder: (context, state) {
        final errors = state is SeasonFormEditing
            ? state.errors
            : const <String, String>{};
        final submitError = state is SeasonFormEditing
            ? state.submitError
            : null;
        final submitting = state is SeasonFormSubmitting;
        final cropItems = <String, String>{
          for (final c in widget.catalog) c.cropId: c.label,
          // محصول مُخزَّن خارج الفهرس يبقى قابلاً للاختيار كما هو.
          if (_crop != null && !widget.catalog.any((c) => c.cropId == _crop))
            _crop!: _crop!,
        };
        return AppScaffold(
          title: _isEdit ? 'تعديل الموسم' : 'موسم جديد',
          padded: true,
          body: ListView(
            padding: const EdgeInsetsDirectional.only(bottom: SahoolSpacing.xl),
            children: [
              if (!_isEdit && widget.hasActiveSeason)
                Padding(
                  padding: const EdgeInsetsDirectional.only(
                    top: SahoolSpacing.md,
                  ),
                  child: Row(
                    children: [
                      Icon(
                        Icons.warning_amber_rounded,
                        color: context.tokens.warning,
                      ),
                      const SizedBox(width: SahoolSpacing.sm),
                      const Expanded(
                        child: Text(
                          'حفظ موسم جديد يُغلق الموسم النشط الحاليّ.',
                        ),
                      ),
                    ],
                  ),
                ),
              if (_useCatalog)
                AppDropdown<String>(
                  key: const ValueKey('season_crop'),
                  label: 'المحصول',
                  items: cropItems,
                  value: _crop,
                  onChanged: submitting
                      ? null
                      : (v) => setState(() => _crop = v),
                )
              else
                AppTextField(
                  key: const ValueKey('season_crop_text'),
                  label: 'المحصول',
                  controller: _cropText,
                  helper:
                      'فهرس المحاصيل غير متاح الآن — اكتب الاسم. قد لا تتوفّر '
                      'مراحل النموّ لمحصول غير معروف للخادم.',
                ),
              if (errors[SeasonFormField.crop] != null)
                _InlineError(errors[SeasonFormField.crop]!),
              AppTextField(
                key: const ValueKey('season_cultivar'),
                label: 'الصنف (اختياريّ)',
                controller: _cultivar,
                errorText: errors[SeasonFormField.cultivar],
              ),
              AppDropdown<String>(
                label: 'نوع الريّ (اختياريّ)',
                items: kIrrigationTypesAr,
                value: _irrigation,
                onChanged: submitting
                    ? null
                    : (v) => setState(() => _irrigation = v),
              ),
              _DateTile(
                key: const ValueKey('season_sowing'),
                label: 'تاريخ الزراعة',
                value: _sowing,
                error: errors[SeasonFormField.sowing],
                onTap: submitting ? null : () => _pickDate(sowing: true),
              ),
              _DateTile(
                key: const ValueKey('season_end'),
                label: 'الحصاد المتوقّع (اختياريّ)',
                value: _end,
                error: errors[SeasonFormField.end],
                onTap: submitting ? null : () => _pickDate(sowing: false),
                onClear:
                    _end == null ||
                        submitting ||
                        widget.original?.seasonEnd != null
                    ? null
                    : () => setState(() => _end = null),
              ),
              AppTextField(
                key: const ValueKey('season_yield'),
                label: 'الإنتاجيّة المستهدفة (اختياريّ)',
                controller: _yield,
                keyboardType: const TextInputType.numberWithOptions(
                  decimal: true,
                ),
                inputFormatters: const [LocalizedDigitsFormatter()],
                helper: 'كجم/هـ',
                errorText: errors[SeasonFormField.targetYield],
              ),
              AppTextField(
                label: 'ملاحظات (اختياريّ)',
                controller: _notes,
                maxLines: 3,
                errorText: errors[SeasonFormField.notes],
              ),
              if (submitError != null) _InlineError(submitError),
              const SizedBox(height: SahoolSpacing.lg),
              PrimaryButton(
                key: const ValueKey('season_submit'),
                label: _isEdit ? 'حفظ التعديلات' : 'حفظ الموسم',
                icon: Icons.save_outlined,
                loading: submitting,
                onPressed: submitting ? null : _submit,
              ),
            ],
          ),
        );
      },
    );
  }
}

class _InlineError extends StatelessWidget {
  const _InlineError(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsetsDirectional.only(top: SahoolSpacing.sm),
    child: Semantics(
      liveRegion: true,
      child: Text(
        text,
        style: context.textStyles.bodyMedium?.copyWith(
          color: context.tokens.danger,
        ),
      ),
    ),
  );
}

/// صفّ اختيار تاريخ بارتفاع لمس ≥48 يعرض التاريخ بأسماء الأشهر العربيّة.
class _DateTile extends StatelessWidget {
  const _DateTile({
    super.key,
    required this.label,
    required this.value,
    required this.onTap,
    this.error,
    this.onClear,
  });

  final String label;
  final DateTime? value;
  final VoidCallback? onTap;
  final VoidCallback? onClear;
  final String? error;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    return Padding(
      padding: const EdgeInsetsDirectional.only(top: SahoolSpacing.md),
      child: InkWell(
        onTap: onTap,
        borderRadius: SahoolRadius.mdAll,
        child: InputDecorator(
          decoration: InputDecoration(
            labelText: label,
            errorText: error,
            prefixIcon: const Icon(Icons.event_outlined),
            suffixIcon: onClear == null
                ? null
                : AppIconButton(
                    icon: Icons.clear,
                    tooltip: 'مسح التاريخ',
                    onPressed: onClear,
                  ),
          ),
          child: ConstrainedBox(
            constraints: const BoxConstraints(
              minHeight: SahoolSizes.minTouchTarget - 24,
            ),
            child: Text(
              value == null ? 'اختر التاريخ' : fmtDate(value),
              style: context.textStyles.bodyLarge?.copyWith(
                color: value == null ? t.muted : null,
              ),
            ),
          ),
        ),
      ),
    );
  }
}
