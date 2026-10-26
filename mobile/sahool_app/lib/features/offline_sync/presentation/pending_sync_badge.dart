// SAHOOL — features/offline_sync/presentation/pending_sync_badge.dart
// شارة عامّة تضعها أيّ ميزة في شريطها (AppBar.actions مثلاً): أيقونة سحابة بعدد
// العمليّات المنتظرة للمستخدم الحاليّ، حمراء إن رفض الخادم شيئاً. لا تظهر حين لا
// شيء ينتظر. الضغط يفتح صفحة حالة المزامنة.
//
//   actions: const [PendingSyncBadge()],
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_navigator.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/features/offline_sync/data/durable_offline_outbox.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';
import 'package:sahool_app/features/offline_sync/offline_sync_routes.dart';

class PendingSyncBadge extends StatefulWidget {
  const PendingSyncBadge({super.key, this.outbox, this.onTap});

  /// الافتراضيّ [OfflineOutbox.instance].
  final OfflineOutbox? outbox;

  /// الافتراضيّ فتح صفحة حالة المزامنة.
  final VoidCallback? onTap;

  @override
  State<PendingSyncBadge> createState() => _PendingSyncBadgeState();
}

class _PendingSyncBadgeState extends State<PendingSyncBadge> {
  late Stream<(int, int)> _counts;

  @override
  void initState() {
    super.initState();
    _counts = _countsOf(widget.outbox ?? OfflineOutbox.instance);
  }

  @override
  void didUpdateWidget(PendingSyncBadge old) {
    super.didUpdateWidget(old);
    if (old.outbox != widget.outbox) {
      _counts = _countsOf(widget.outbox ?? OfflineOutbox.instance);
    }
  }

  static Stream<(int, int)> _countsOf(OfflineOutbox outbox) =>
      outbox is DurableOfflineOutbox
      ? outbox.watch().map((s) => (s.pending.length, s.rejected.length))
      : outbox.pendingCount.map((n) => (n, 0));

  @override
  Widget build(BuildContext context) => StreamBuilder<(int, int)>(
    stream: _counts,
    builder: (context, snap) {
      final (pending, rejected) = snap.data ?? (0, 0);
      final total = pending + rejected;
      if (total == 0) return const SizedBox.shrink();
      final t = context.tokens;
      final scheme = Theme.of(context).colorScheme;
      final attention = rejected > 0;
      final tooltip = attention
          ? 'المزامنة: $pending بانتظار الإرسال، $rejected مرفوضة'
          : 'المزامنة: $pending بانتظار الإرسال';
      return IconButton(
        key: const ValueKey('pending-sync-badge'),
        tooltip: tooltip,
        constraints: const BoxConstraints(
          minWidth: SahoolSizes.minTouchTarget,
          minHeight: SahoolSizes.minTouchTarget,
        ),
        onPressed:
            widget.onTap ??
            () => context.openRoute<void>(OfflineSyncRoutes.status),
        icon: Badge(
          label: Text(total > 99 ? '99+' : '$total'),
          backgroundColor: attention ? scheme.error : t.warning,
          textColor: attention ? scheme.onError : t.background,
          child: Icon(
            attention
                ? Icons.sync_problem_rounded
                : Icons.cloud_upload_outlined,
          ),
        ),
      );
    },
  );
}
