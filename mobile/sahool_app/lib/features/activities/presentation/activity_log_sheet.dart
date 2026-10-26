// SAHOOL — features/activities/presentation/activity_log_sheet.dart
// التسجيل السريع لنشاط حقل: نوع بنقرة (رقائق كبيرة بأيقونات)، «نُفِّذ اليوم»
// افتراضيّاً، وعنوان/ملاحظة اختياريّان. يعمل بلا اتّصال عبر صندوق الإرسال.
//
// * أنواع الخادم فقط (لا «أخرى»: الخادم يرفضها بـ422).
// * تحقّق سطريّ: النوع مطلوب، العنوان ≤200، تاريخ التنفيذ ليس في المستقبل،
//   تاريخ الجدولة ليس في الماضي.
// * مفتاح Idempotency-Key واحد لعمر الورقة ما دام الجسم نفسه (كاتب واحد لكلّ
//   ورقة)، والزرّ معطّل أثناء الإرسال.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/activities/data/activity_writer.dart';
import 'package:sahool_app/features/activities/data/field_activity.dart';
import 'package:sahool_app/features/tasks/data/offline_write.dart';

import 'activity_labels.dart';

typedef ActivityDatePicker =
    Future<DateTime?> Function(
      BuildContext context, {
      required DateTime initial,
      required DateTime first,
      required DateTime last,
    });

Future<DateTime?> materialActivityDatePicker(
  BuildContext context, {
  required DateTime initial,
  required DateTime first,
  required DateTime last,
}) => showDatePicker(
  context: context,
  initialDate: initial,
  firstDate: first,
  lastDate: last,
);

/// رسالة نتيجة التسجيل للمستدعي (SnackBar بعد إغلاق الورقة).
String activityOutcomeMessage(
  WriteOutcome<FieldActivity> o,
) => switch (o.kind) {
  WriteOutcomeKind.saved => 'سُجِّل النشاط.',
  WriteOutcomeKind.queued =>
    'لا اتّصال — حُفظ النشاط على هذا الجهاز وسيُرسَل تلقائيّاً عند عودة الشبكة.',
  WriteOutcomeKind.failed => o.messageAr,
};

/// يفتح ورقة التسجيل لحقل. يُرجِع النتيجة (محفوظ/مُودَع) أو null إن أُغلقت.
Future<WriteOutcome<FieldActivity>?> showActivityLogSheet(
  BuildContext context, {
  required String fieldId,
  String? fieldName,
  ActivityWriter? writer,
}) => showAppBottomSheet<WriteOutcome<FieldActivity>>(
  context,
  builder: (_) =>
      ActivityLogSheet(fieldId: fieldId, fieldName: fieldName, writer: writer),
);

class ActivityLogSheet extends StatefulWidget {
  const ActivityLogSheet({
    super.key,
    required this.fieldId,
    this.fieldName,
    this.writer,
    this.clock,
    this.pickDate,
    this.popOnDone = true,
    this.onDone,
  });

  final String fieldId;
  final String? fieldName;
  final ActivityWriter? writer;
  final DateTime Function()? clock;
  final ActivityDatePicker? pickDate;

  /// true ⇒ تُغلَق الورقة بالنتيجة عند النجاح.
  final bool popOnDone;
  final ValueChanged<WriteOutcome<FieldActivity>>? onDone;

  @override
  State<ActivityLogSheet> createState() => _ActivityLogSheetState();
}

class _ActivityLogSheetState extends State<ActivityLogSheet> {
  late final ActivityWriter _writer = widget.writer ?? ActivityWriter();
  final _title = TextEditingController();
  final _notes = TextEditingController();
  ActivityDraft _draft = const ActivityDraft();
  Map<String, String> _errors = const {};
  String? _submitError;
  bool _submitting = false;

  DateTime get _now => (widget.clock ?? DateTime.now)();

  @override
  void dispose() {
    _title.dispose();
    _notes.dispose();
    super.dispose();
  }

  Future<void> _chooseDate() async {
    final now = _now;
    final today = DateTime(now.year, now.month, now.day);
    final planned = _draft.when == ActivityWhen.planned;
    final first = planned ? today : today.subtract(const Duration(days: 730));
    final last = planned ? today.add(const Duration(days: 365)) : today;
    final picked = await (widget.pickDate ?? materialActivityDatePicker)(
      context,
      initial: _draft.date ?? today,
      first: first,
      last: last,
    );
    if (!mounted || picked == null) return;
    setState(() {
      _draft = _draft.copyWith(date: picked);
      _errors = Map.of(_errors)..remove('date');
    });
  }

  Future<void> _submit() async {
    if (_submitting) return;
    final draft = _draft.copyWith(title: _title.text, notes: _notes.text);
    final now = _now;
    final errors = draft.validate(now);
    if (errors.isNotEmpty) {
      setState(() {
        _draft = draft;
        _errors = errors;
        _submitError = null;
      });
      return;
    }
    setState(() {
      _draft = draft;
      _errors = const {};
      _submitError = null;
      _submitting = true;
    });
    final outcome = await _writer.submit(
      widget.fieldId,
      draft.toJson(now),
      typeLabelAr: activityTypeAr(draft.type!),
    );
    if (!mounted) return;
    if (outcome.isFailed) {
      setState(() {
        _submitting = false;
        _submitError = outcome.messageAr;
      });
      return;
    }
    widget.onDone?.call(outcome);
    if (widget.popOnDone) {
      Navigator.of(context).pop(outcome);
    } else {
      setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final errStyle = context.textStyles.bodySmall?.copyWith(color: t.danger);
    final date = _draft.date;
    return AppSheet(
      title: 'تسجيل نشاط',
      submitLabel: 'حفظ النشاط',
      onSubmit: _submit,
      submitting: _submitting,
      errorText: _submitError,
      children: [
        if (widget.fieldName != null) ...[
          const SizedBox(height: SahoolSpacing.xs),
          Text(
            widget.fieldName!,
            style: context.textStyles.bodyMedium?.copyWith(color: t.muted),
          ),
        ],
        const SizedBox(height: SahoolSpacing.lg),
        Text('نوع النشاط', style: context.textStyles.titleSmall),
        const SizedBox(height: SahoolSpacing.sm),
        Wrap(
          spacing: SahoolSpacing.sm,
          runSpacing: SahoolSpacing.sm,
          children: [
            for (final type in kActivityTypes)
              ChoiceChip(
                avatar: Icon(activityTypeIcon(type), size: SahoolSizes.iconSm),
                label: Text(activityTypeAr(type)),
                selected: _draft.type == type,
                onSelected: _submitting
                    ? null
                    : (_) => setState(() {
                        _draft = _draft.copyWith(type: type);
                        _errors = Map.of(_errors)..remove('type');
                      }),
              ),
          ],
        ),
        if (_errors['type'] != null) ...[
          const SizedBox(height: SahoolSpacing.xs),
          Text(_errors['type']!, style: errStyle),
        ],
        const SizedBox(height: SahoolSpacing.lg),
        Text('متى؟', style: context.textStyles.titleSmall),
        const SizedBox(height: SahoolSpacing.sm),
        Wrap(
          spacing: SahoolSpacing.sm,
          runSpacing: SahoolSpacing.sm,
          children: [
            for (final (w, label) in const [
              (ActivityWhen.today, 'نُفِّذ اليوم'),
              (ActivityWhen.onDate, 'نُفِّذ في يوم آخر'),
              (ActivityWhen.planned, 'مُجدوَل لاحقاً'),
            ])
              ChoiceChip(
                label: Text(label),
                selected: _draft.when == w,
                onSelected: _submitting
                    ? null
                    : (_) => setState(() {
                        _draft = _draft.copyWith(when: w, clearDate: true);
                        _errors = Map.of(_errors)..remove('date');
                      }),
              ),
          ],
        ),
        if (_draft.when != ActivityWhen.today) ...[
          const SizedBox(height: SahoolSpacing.sm),
          SecondaryButton(
            label: date == null
                ? (_draft.when == ActivityWhen.planned
                      ? 'اختر تاريخ الجدولة'
                      : 'اختر تاريخ التنفيذ')
                : fmtDate(date),
            icon: Icons.calendar_month_outlined,
            onPressed: _submitting ? null : _chooseDate,
          ),
          if (_errors['date'] != null) ...[
            const SizedBox(height: SahoolSpacing.xs),
            Text(_errors['date']!, style: errStyle),
          ],
        ],
        AppTextField(
          label: 'العنوان (اختياريّ)',
          hint: 'مثال: رشّ مبيد فطريّ',
          controller: _title,
          errorText: _errors['title'],
          enabled: !_submitting,
        ),
        AppTextField(
          label: 'ملاحظات (اختياريّة)',
          controller: _notes,
          maxLines: 3,
          errorText: _errors['notes'],
          enabled: !_submitting,
        ),
      ],
    );
  }
}
