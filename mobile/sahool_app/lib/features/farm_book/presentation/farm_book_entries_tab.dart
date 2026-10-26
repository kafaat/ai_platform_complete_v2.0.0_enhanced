// SAHOOL — features/farm_book/presentation/farm_book_entries_tab.dart
// قائمة قيود الشهر، وتفاصيل القيد مع «عكس القيد». التصحيح في هذا الدفتر عكسٌ لا
// تعديل: الخادم لا يملك تعديل قيد ولا حذفه، بل قيداً مرآةً يلغي أثره.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

import '../data/farm_book_models.dart';
import 'farm_book_cubit.dart';
import 'farm_book_state.dart';
import 'farm_book_text.dart';

class FarmBookEntriesTab extends StatelessWidget {
  const FarmBookEntriesTab({super.key, required this.onAdd});
  final VoidCallback onAdd;

  @override
  Widget build(BuildContext context) {
    return BlocBuilder<FarmBookCubit, FarmBookState>(
      builder: (context, state) {
        final cubit = context.read<FarmBookCubit>();
        final entries = state.entries;
        return switch (entries) {
          SectionLoading() || SectionNotAllowed() => const LoadingState(
            message: 'جارٍ تحميل القيود…',
          ),
          SectionFailed(:final error) => ErrorState(
            error: error,
            onRetry: cubit.loadBook,
          ),
          SectionLoaded(:final data) when data.isEmpty => EmptyState(
            icon: Icons.receipt_long_outlined,
            message: 'لا قيود في هذا الشهر.',
            actionLabel: cubit.access.canWrite ? 'أضف قيداً' : null,
            onAction: cubit.access.canWrite ? onAdd : null,
          ),
          SectionLoaded(:final data) => RefreshIndicator(
            onRefresh: cubit.loadBook,
            child: ListView.separated(
              padding: const EdgeInsetsDirectional.fromSTEB(
                SahoolSpacing.page,
                SahoolSpacing.sm,
                SahoolSpacing.page,
                SahoolSpacing.xxl * 3,
              ),
              itemCount: data.length,
              separatorBuilder: (_, _) =>
                  const SizedBox(height: SahoolSpacing.sm),
              itemBuilder: (context, i) => FarmBookEntryTile(
                entry: data[i],
                reversed: state.reversedIds.contains(data[i].entryId),
                onTap: () => _openDetails(context, data[i]),
              ),
            ),
          ),
        };
      },
    );
  }

  Future<void> _openDetails(BuildContext context, FarmBookEntry entry) async {
    final cubit = context.read<FarmBookCubit>();
    final messenger = ScaffoldMessenger.of(context);
    final outcome = await showAppBottomSheet<FarmBookWriteOutcome>(
      context,
      builder: (_) => EntryDetailsSheet(cubit: cubit, entry: entry),
    );
    if (outcome == null) return;
    messenger.showSnackBar(
      SnackBar(
        content: Text(switch (outcome) {
          WriteSaved() => 'سُجّل القيد العكسي؛ أثر القيد الأصليّ أُلغي.',
          WriteQueued() =>
            'لا اتّصال: حُفظ العكس في صندوق الإرسال وسيُرسَل عند عودة الشبكة.',
          WriteFailed(:final messageAr) => messageAr,
        }),
      ),
    );
  }
}

class FarmBookEntryTile extends StatelessWidget {
  const FarmBookEntryTile({
    super.key,
    required this.entry,
    required this.reversed,
    this.onTap,
  });

  final FarmBookEntry entry;
  final bool reversed;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final (icon, color) = switch (entry.entryType) {
      'income' => (Icons.south_west_rounded, t.success),
      'expense' => (Icons.north_east_rounded, t.danger),
      _ => (Icons.swap_horiz_rounded, t.info),
    };
    final faded = reversed || entry.isReversal;
    final subtitle = [
      fmtIsoDate(entry.occurredOn),
      paymentMethodLabel(entry.paymentMethod),
      if (entry.partyName != null) entry.partyName!,
    ].join(' · ');
    return Card(
      margin: EdgeInsets.zero,
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(
            minHeight: SahoolSizes.minTouchTarget + 8,
          ),
          child: Padding(
            padding: const EdgeInsets.all(SahoolSpacing.md),
            child: Row(
              children: [
                Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    color: color.withValues(alpha: 0.12),
                    borderRadius: SahoolRadius.mdAll,
                  ),
                  child: Icon(icon, color: color),
                ),
                const SizedBox(width: SahoolSpacing.md),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '${entryTypeLabel(entry.entryType)}: '
                        '${categoryLabel(entry.category)}',
                        style: context.textStyles.titleSmall,
                      ),
                      const SizedBox(height: SahoolSpacing.xxs),
                      Text(subtitle, style: context.textStyles.bodySmall),
                      if (reversed || entry.isReversal) ...[
                        const SizedBox(height: SahoolSpacing.xs),
                        StatusChip(
                          label: entry.isReversal
                              ? 'قيد عكسي (تصحيح)'
                              : 'معكوس',
                          tone: StatusTone.warning,
                          icon: Icons.undo_rounded,
                        ),
                      ],
                    ],
                  ),
                ),
                const SizedBox(width: SahoolSpacing.sm),
                Text(
                  fmtMoney(entry.amount, entry.currency),
                  style: context.textStyles.titleSmall?.copyWith(
                    color: faded ? t.muted : color,
                    decoration: faded ? TextDecoration.lineThrough : null,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// تفاصيل قيد + عكسه بعد تأكيد. مفتاح منع التكرار يُولَّد مرّة عند فتح الورقة
/// (نيّة العكس) ويُعاد في كلّ محاولة.
class EntryDetailsSheet extends StatefulWidget {
  const EntryDetailsSheet({
    super.key,
    required this.cubit,
    required this.entry,
  });
  final FarmBookCubit cubit;
  final FarmBookEntry entry;

  @override
  State<EntryDetailsSheet> createState() => _EntryDetailsSheetState();
}

class _EntryDetailsSheetState extends State<EntryDetailsSheet> {
  final IdempotencyKey _key = IdempotencyKey.generate();
  bool _submitting = false;
  String? _error;

  Future<void> _reverse() async {
    if (_submitting) return;
    final e = widget.entry;
    final today = widget.cubit.today;
    final crossMonth = !e.occurredOn.startsWith(today.substring(0, 7));
    final ok = await showConfirmDialog(
      context,
      title: 'عكس القيد؟',
      message:
          'سيُسجَّل قيد عكسي بتاريخ اليوم بالمبلغ نفسه '
          '(${fmtMoney(e.amount, e.currency)}) فيُلغي أثر هذا القيد. '
          'لا يُحذف القيد الأصليّ ولا يمكن عكس العكس.'
          '${crossMonth ? '\nالقيد الأصليّ في شهر سابق: سيظهر العكس سالباً في تقرير هذا الشهر.' : ''}',
      confirmLabel: 'اعكس القيد',
      destructive: true,
    );
    if (!ok || !mounted) return;
    setState(() {
      _submitting = true;
      _error = null;
    });
    final outcome = await widget.cubit.reverse(e, _key);
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
    final e = widget.entry;
    final cubit = widget.cubit;
    final block = cubit.reversalBlockReason(e);
    final field = cubit.state.fieldOptions
        .where((f) => f.id == e.fieldId)
        .map((f) => f.name)
        .firstOrNull;
    return AppSheet(
      title: '${entryTypeLabel(e.entryType)}: ${categoryLabel(e.category)}',
      errorText: _error,
      children: [
        const SizedBox(height: SahoolSpacing.md),
        _Row('المبلغ', fmtMoney(e.amount, e.currency)),
        _Row('التاريخ', fmtIsoDate(e.occurredOn)),
        _Row('الدفع', paymentMethodLabel(e.paymentMethod)),
        _Row('الطرف', e.partyName ?? '—'),
        if (e.fieldId != null) _Row('الحقل', field ?? e.fieldId!),
        if (e.description != null) _Row('ملاحظة', e.description!),
        if (e.isReversal) const _Row('تصحيح', 'هذا قيد عكسي يلغي أثر قيد سابق'),
        if (cubit.access.canWrite) ...[
          const SizedBox(height: SahoolSpacing.lg),
          if (block != null)
            Text(
              block,
              style: context.textStyles.bodyMedium?.copyWith(
                color: context.tokens.muted,
              ),
            )
          else
            PrimaryButton(
              label: 'عكس القيد (تصحيح)',
              icon: Icons.undo_rounded,
              tone: ButtonTone.danger,
              loading: _submitting,
              onPressed: _reverse,
            ),
        ],
      ],
    );
  }
}

class _Row extends StatelessWidget {
  const _Row(this.label, this.value);
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: SahoolSpacing.xs),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 96,
          child: Text(
            label,
            style: context.textStyles.bodyMedium?.copyWith(
              color: context.tokens.muted,
            ),
          ),
        ),
        Expanded(child: Text(value, style: context.textStyles.bodyLarge)),
      ],
    ),
  );
}
