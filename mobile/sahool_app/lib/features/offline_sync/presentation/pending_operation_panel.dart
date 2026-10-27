// SAHOOL — features/offline_sync/presentation/pending_operation_panel.dart
// لوحة عمليّة إنشاء غير محسومة (operation_ledger.dart): الرسالة الصادقة، فروق
// المسودّة التي لم تُرسَل، وزرّ «استعادة نتيجة المحاولة السابقة» (نفس المفتاح ونفس
// الحمولة). لا زرّ «أنشئ من جديد» ولا مفتاح جديد (OD-2). الإغلاق اليدويّ يظهر فقط
// بعد انقضاء مدّة احتفاظ الخادم (needs_reconciliation).
import 'package:flutter/material.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/offline_sync/data/operation_ledger.dart';

/// قيمة مقروءة لحقل حمولة (الهندسة وما شابه تُعرَض «قيمة مركّبة» لا خاماً).
String describePayloadValue(Object? v) {
  if (v == null || (v is String && v.trim().isEmpty)) return '—';
  if (v is String || v is num || v is bool) return v.toString();
  if (v is List && v.every((e) => e is String || e is num)) {
    return v.join('، ');
  }
  return 'قيمة مركّبة';
}

class PayloadChangesList extends StatelessWidget {
  const PayloadChangesList({
    super.key,
    required this.changes,
    this.labels = const {},
  });

  final List<PayloadChange> changes;

  /// أسماء عربيّة لمفاتيح الحمولة.
  final Map<String, String> labels;

  @override
  Widget build(BuildContext context) => Column(
    key: const ValueKey('pending-op-diff'),
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      for (final c in changes)
        Padding(
          padding: const EdgeInsets.only(top: SahoolSpacing.xs),
          child: Text(
            '${labels[c.key] ?? c.key}: ${describePayloadValue(c.before)} ← '
            '${describePayloadValue(c.after)}',
            style: context.textStyles.bodyMedium,
          ),
        ),
    ],
  );
}

class PendingOperationPanel extends StatelessWidget {
  const PendingOperationPanel({
    super.key,
    required this.outcome,
    required this.onRecover,
    this.onDismiss,
    this.labels = const {},
    this.busy = false,
  });

  final CreateUnconfirmed outcome;
  final VoidCallback onRecover;
  final VoidCallback? onDismiss;
  final Map<String, String> labels;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final changes = outcome.draftChanges;
    return Container(
      key: const ValueKey('pending-op-panel'),
      width: double.infinity,
      padding: const EdgeInsets.all(SahoolSpacing.md),
      decoration: BoxDecoration(
        color: t.warning.withValues(alpha: 0.10),
        borderRadius: SahoolRadius.mdAll,
        border: Border.all(color: t.warning.withValues(alpha: 0.5)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Semantics(
            liveRegion: true,
            child: Text(
              outcome.messageAr,
              key: const ValueKey('pending-op-message'),
              style: context.textStyles.bodyLarge,
            ),
          ),
          if (changes.isNotEmpty) ...[
            const SizedBox(height: SahoolSpacing.sm),
            Text(
              'تعديلاتك محفوظة ولم تُرسَل (تُعرَض للتحديث بعد الاستعادة):',
              style: context.textStyles.bodyMedium?.copyWith(color: t.muted),
            ),
            PayloadChangesList(changes: changes, labels: labels),
          ],
          const SizedBox(height: SahoolSpacing.md),
          PrimaryButton(
            key: const ValueKey('pending-op-recover'),
            label: outcome.actionLabelAr,
            icon: Icons.history_rounded,
            loading: busy,
            onPressed: busy ? null : onRecover,
          ),
          if (outcome.canDismiss && onDismiss != null) ...[
            const SizedBox(height: SahoolSpacing.sm),
            SecondaryButton(
              key: const ValueKey('pending-op-dismiss'),
              label: kDismissReconciledAr,
              onPressed: busy ? null : onDismiss,
            ),
          ],
        ],
      ),
    );
  }
}
