// SAHOOL — features/crop_season/presentation/season_form_screen.dart
// إنشاء/تعديل موسم: المحصول من الفهرس (بلا كتابة)، الصنف، الريّ، تاريخ الزراعة،
// الحصاد المتوقّع، الإنتاجيّة المستهدفة، ملاحظات. التواريخ تُعرَض بأسماء الأشهر
// العربيّة (fmtDate) وتُرسَل «YYYY-MM-DD». الأخطاء سطريّة تحت الحقل.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/offline_sync/data/operation_ledger.dart';
import 'package:sahool_app/features/offline_sync/presentation/pending_operation_panel.dart';

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
    this.ledger,
  });

  final String fieldId;
  final Season? original;
  final List<CropOption> catalog;

  /// إنشاء موسم جديد يُغلق الموسم النشط الحاليّ على الخادم — نحذّر قبله.
  final bool hasActiveSeason;
  final CropSeasonApi? api;

  /// قابل للحقن في الاختبارات.
  final DateTime? today;

  /// سجلّ عمليّات الإنشاء المعلّقة (للاختبار)؛ null ⇒ السجلّ المشترك.
  final OperationLedger? ledger;

  @override
  Widget build(BuildContext context) => BlocProvider(
    // restore: إنشاءٌ سابق لم تُحسَم نتيجته لنفس المالك والحقل يظهر قبل أيّ إنشاء.
    create: (_) => SeasonFormCubit(
      api ?? CropSeasonApi.instance,
      fieldId: fieldId,
      original: original,
      ledger: ledger,
    )..restore(),
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

  // يُقرأ هنا لا في dispose (لا بحث عن السلف عند التفكيك).
  late SeasonFormCubit _cubit;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _cubit = context.read<SeasonFormCubit>();
  }

  @override
  void dispose() {
    // إغلاق الشاشة بعد نتيجة مجهولة لا يُضيّع التعديلات: تُحفَظ مسودّةً (لا تُرسَل).
    if (_cubit.state is SeasonFormUnconfirmed) {
      unawaited(_cubit.rememberDraft(_input()));
    }
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
        final unconfirmed = state is SeasonFormUnconfirmed ? state : null;
        final recovered = state is SeasonFormRecovered ? state : null;
        final submitting =
            state is SeasonFormSubmitting || (unconfirmed?.busy ?? false);
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
              if (unconfirmed != null)
                Padding(
                  padding: const EdgeInsetsDirectional.only(
                    top: SahoolSpacing.md,
                  ),
                  child: PendingOperationPanel(
                    outcome: unconfirmed.outcome,
                    busy: unconfirmed.busy,
                    labels: kSeasonFieldLabelsAr,
                    onRecover: () => context.read<SeasonFormCubit>().recover(
                      draft: _input(),
                    ),
                    onDismiss: context
                        .read<SeasonFormCubit>()
                        .dismissReconciled,
                  ),
                ),
              if (recovered != null) _recoveredCard(context, recovered),
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
              // إنشاءٌ غير محسوم ⇒ لا زرّ إنشاء؛ الاستعادة من اللوحة وحدها (OD-2).
              if (unconfirmed == null && recovered == null)
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

/// أسماء مفاتيح حمولة الموسم في فروق المسودّة.
const Map<String, String> kSeasonFieldLabelsAr = {
  'crops': 'المحصول',
  'cultivar': 'الصنف',
  'irrigation_type': 'نوع الريّ',
  'sowing_date': 'تاريخ الزراعة',
  'season_end': 'الحصاد المتوقّع',
  'target_yield_kg_ha': 'الإنتاجيّة المستهدفة',
  'notes_ar': 'ملاحظات',
};

Widget _recoveredCard(BuildContext context, SeasonFormRecovered s) {
  final cubit = context.read<SeasonFormCubit>();
  return Padding(
    padding: const EdgeInsetsDirectional.only(top: SahoolSpacing.md),
    child: SectionCard(
      title: 'استُعيد الموسم المُنشأ',
      icon: Icons.history_rounded,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'أُنشئ الموسم بالقيم المرسلة أوّلاً. تعديلاتك التالية لم تُرسَل؛ '
            'تطبيقها تحديثٌ منفصل للموسم نفسه:',
            key: const ValueKey('pending-op-recovered'),
            style: context.textStyles.bodyLarge,
          ),
          PayloadChangesList(
            changes: s.pendingEdits,
            labels: kSeasonFieldLabelsAr,
          ),
          if (s.applyError != null) _InlineError(s.applyError!),
          const SizedBox(height: SahoolSpacing.md),
          PrimaryButton(
            key: const ValueKey('season_apply_edits'),
            label: 'تطبيق التعديلات على الموسم',
            icon: Icons.edit_outlined,
            loading: s.busy,
            onPressed: s.busy ? null : cubit.applyPendingEdits,
          ),
          const SizedBox(height: SahoolSpacing.sm),
          SecondaryButton(
            key: const ValueKey('season_keep_recovered'),
            label: 'الإبقاء على الموسم كما أُنشئ',
            onPressed: s.busy ? null : cubit.keepRecovered,
          ),
        ],
      ),
    ),
  );
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
