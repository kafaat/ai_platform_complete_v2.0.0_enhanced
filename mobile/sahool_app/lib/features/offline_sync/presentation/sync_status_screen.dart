// SAHOOL — features/offline_sync/presentation/sync_status_screen.dart
// صفحة «حالة المزامنة»: ما سُجِّل دون اتّصال ولم يصل الخادم بعد، وما رفضه الخادم
// برسالته. لا شيء يُحذف إلّا بيد المستخدم وبعد تأكيد.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/connectivity_status.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/offline_sync/data/durable_offline_outbox.dart';
import 'package:sahool_app/features/offline_sync/data/outbox_record.dart';
import 'package:sahool_app/features/offline_sync/data/outbox_store.dart';

import 'sync_status_cubit.dart';

/// وصف عربيّ لأنواع العمليّات المعروفة؛ غيرها يُعرَض باسمه كما أُودع.
String outboxKindLabelAr(String kind) => switch (kind) {
  'task_update' => 'تحديث مهمّة',
  'observation_create' => 'ملاحظة استكشاف',
  'activity_create' || 'activity_complete' => 'نشاط حقليّ',
  'scouting_pin_create' => 'نقطة استكشاف',
  'season_create' => 'إنشاء موسم',
  'water_applied' => 'قيد ريّ في دفتر المياه',
  'inventory_batch_add' => 'إضافة دفعة مخزون',
  'equipment_maintenance_log' => 'سجلّ صيانة معدّة',
  'lab_sample_create' => 'عيّنة مختبر',
  'farm_book_entry' => 'قيد في دفتر المزرعة',
  _ => kind,
};

String outboxTitleAr(OutboxRecord r) {
  final label = r.op.labelAr;
  return (label != null && label.trim().isNotEmpty)
      ? label
      : outboxKindLabelAr(r.op.kind);
}

class SyncStatusScreen extends StatelessWidget {
  const SyncStatusScreen({super.key, this.outbox, this.connectivity, this.now});

  /// يُحقَن في الاختبارات؛ الافتراضيّ الصندوق المشترك.
  final DurableOfflineOutbox? outbox;
  final ValueNotifier<bool>? connectivity;
  final DateTime Function()? now;

  @override
  Widget build(BuildContext context) => BlocProvider(
    create: (_) => SyncStatusCubit(outbox ?? DurableOfflineOutbox.shared),
    child: SyncStatusView(
      connectivity: connectivity ?? ConnectivityStatus.instance,
      now: now ?? DateTime.now,
    ),
  );
}

class SyncStatusView extends StatelessWidget {
  const SyncStatusView({
    super.key,
    required this.connectivity,
    required this.now,
  });

  final ValueNotifier<bool> connectivity;
  final DateTime Function() now;

  @override
  Widget build(BuildContext context) {
    final cubit = context.read<SyncStatusCubit>();
    return AppScaffold(
      title: 'حالة المزامنة',
      onRefresh: cubit.sendAll,
      body: BlocBuilder<SyncStatusCubit, SyncStatusState>(
        builder: (context, state) => switch (state) {
          SyncStatusLoading() => const LoadingState(
            message: 'جارٍ فتح صندوق المزامنة',
          ),
          SyncStatusUnavailable() => _Unavailable(state: state),
          SyncStatusLoaded() => ValueListenableBuilder<bool>(
            valueListenable: connectivity,
            builder: (context, online, _) =>
                _Loaded(state: state, online: online, now: now()),
          ),
        },
      ),
    );
  }
}

class _Unavailable extends StatelessWidget {
  const _Unavailable({required this.state});
  final SyncStatusUnavailable state;

  @override
  Widget build(BuildContext context) {
    final canReset =
        state.failure.failure == OutboxStoreFailure.keyMissingForExistingBox;
    return EmptyState(
      icon: Icons.lock_outline_rounded,
      title: 'صندوق المزامنة غير متاح',
      message: canReset
          ? '${state.failure.messageAr} يمكنك حذفه لبدء صندوق جديد؛ ما فيه لا يمكن استعادته.'
          : state.failure.messageAr,
      actionLabel: canReset && !state.resetting
          ? 'حذف الصندوق غير المقروء'
          : null,
      onAction: canReset && !state.resetting
          ? () async {
              final cubit = context.read<SyncStatusCubit>();
              final ok = await showConfirmDialog(
                context,
                title: 'حذف صندوق المزامنة؟',
                message:
                    'محتواه مشفّر بمفتاح مفقود ولا يمكن إرساله. سيُحذف نهائيّاً من هذا الجهاز.',
                confirmLabel: 'حذف',
                destructive: true,
              );
              if (ok) await cubit.resetUnreadableStore();
            }
          : null,
    );
  }
}

class _Loaded extends StatelessWidget {
  const _Loaded({required this.state, required this.online, required this.now});

  final SyncStatusLoaded state;
  final bool online;
  final DateTime now;

  @override
  Widget build(BuildContext context) {
    final s = state.snapshot;
    if (s.owner == null) {
      return const EmptyState(
        icon: Icons.person_off_outlined,
        message: 'سجّل الدخول لعرض عمليّاتك المنتظرة.',
      );
    }
    final children = <Widget>[
      _Summary(snapshot: s, online: online),
      if (s.heldForOtherAccounts > 0)
        Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(
            SahoolSpacing.lg,
            SahoolSpacing.sm,
            SahoolSpacing.lg,
            0,
          ),
          child: Text(
            '${s.heldForOtherAccounts} عمليّة محفوظة على هذا الجهاز لحساب آخر؛ '
            'لا تُرسَل إلّا حين يدخل صاحبها.',
            style: context.textStyles.bodySmall?.copyWith(
              color: context.tokens.muted,
            ),
          ),
        ),
    ];
    if (state.isEmpty) {
      children.add(
        const Padding(
          padding: EdgeInsets.only(top: SahoolSpacing.xl),
          child: EmptyState(
            icon: Icons.cloud_done_outlined,
            message:
                'لا عمليّات بانتظار المزامنة. كلّ ما سجّلته وصل إلى الخادم.',
          ),
        ),
      );
    }
    if (s.rejected.isNotEmpty) {
      children.add(const ListSectionHeader('تحتاج انتباهك — رفضها الخادم'));
      for (final r in s.rejected) {
        children.add(
          _OpCard(
            record: r,
            busy: state.busy.contains(r.id),
            online: online,
            now: now,
          ),
        );
      }
    }
    if (s.pending.isNotEmpty) {
      children.add(const ListSectionHeader('بانتظار الإرسال'));
      for (final r in s.pending) {
        children.add(
          _OpCard(
            record: r,
            busy: state.busy.contains(r.id),
            online: online,
            now: now,
          ),
        );
      }
    }
    // قائمة قابلة للتمرير دائماً كي يعمل السحب للإرسال.
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.only(bottom: SahoolSpacing.xxl),
      children: children,
    );
  }
}

class _Summary extends StatelessWidget {
  const _Summary({required this.snapshot, required this.online});
  final OutboxSnapshot snapshot;
  final bool online;

  @override
  Widget build(BuildContext context) {
    final pending = snapshot.pending.length;
    final rejected = snapshot.rejected.length;
    return Padding(
      padding: const EdgeInsets.all(SahoolSpacing.lg),
      child: SectionCard(
        title: 'ملخّص',
        icon: Icons.sync_rounded,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Wrap(
              spacing: SahoolSpacing.sm,
              runSpacing: SahoolSpacing.sm,
              children: [
                StatusChip(
                  key: const ValueKey('sync-pending-count'),
                  label: 'بانتظار الإرسال: $pending',
                  tone: pending > 0 ? StatusTone.info : StatusTone.success,
                  icon: Icons.cloud_upload_outlined,
                ),
                StatusChip(
                  key: const ValueKey('sync-rejected-count'),
                  label: 'مرفوضة: $rejected',
                  tone: rejected > 0 ? StatusTone.danger : StatusTone.neutral,
                ),
              ],
            ),
            if (!online) ...[
              const SizedBox(height: SahoolSpacing.md),
              Text(
                'لا اتّصال بالشبكة — ستُرسَل العمليّات تلقائيّاً عند عودته.',
                style: context.textStyles.bodyMedium?.copyWith(
                  color: context.tokens.warning,
                ),
              ),
            ],
            if (pending > 0) ...[
              const SizedBox(height: SahoolSpacing.md),
              PrimaryButton(
                label: 'إرسال الآن',
                icon: Icons.cloud_upload_rounded,
                loading: snapshot.draining,
                onPressed: online
                    ? () => context.read<SyncStatusCubit>().sendAll()
                    : null,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _OpCard extends StatelessWidget {
  const _OpCard({
    required this.record,
    required this.busy,
    required this.online,
    required this.now,
  });

  final OutboxRecord record;
  final bool busy;
  final bool online;
  final DateTime now;

  Future<void> _discard(BuildContext context) async {
    final cubit = context.read<SyncStatusCubit>();
    final ok = await showConfirmDialog(
      context,
      title: 'تجاهل هذه العمليّة؟',
      message:
          'لن تُرسَل «${outboxTitleAr(record)}» إلى الخادم وستُحذف من '
          'هذا الجهاز نهائيّاً.',
      confirmLabel: 'تجاهل',
      destructive: true,
    );
    if (ok) await cubit.discard(record.id);
  }

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final styles = context.textStyles;
    final r = record;
    final field = r.op.fieldId;
    final lines = <Widget>[
      Text(
        outboxKindLabelAr(r.op.kind) == outboxTitleAr(r)
            ? '${r.op.method} ${r.op.path}'
            : outboxKindLabelAr(r.op.kind),
        style: styles.bodySmall?.copyWith(color: t.muted),
      ),
      const SizedBox(height: SahoolSpacing.xs),
      Text(
        field == null || field.isEmpty ? 'بلا حقل محدّد' : 'الحقل: $field',
        style: styles.bodyMedium,
      ),
      Text(
        'سُجِّلت ${fmtAge(r.createdAt.toLocal(), now: now)}',
        style: styles.bodyMedium,
      ),
    ];
    if (r.isRejected) {
      final code = r.rejectedStatus;
      lines.addAll([
        const SizedBox(height: SahoolSpacing.sm),
        StatusChip(
          label: code == null ? 'رفضها الخادم' : 'رفضها الخادم ($code)',
          tone: StatusTone.danger,
        ),
        const SizedBox(height: SahoolSpacing.xs),
        Text(
          r.rejectedMessageAr ?? 'لم يُرسل الخادم سبباً.',
          style: styles.bodyMedium?.copyWith(color: t.danger),
        ),
      ]);
    } else if (r.attempts > 0) {
      final next = r.nextAttemptAt;
      lines.addAll([
        const SizedBox(height: SahoolSpacing.sm),
        Text(
          'محاولات: ${r.attempts}'
          '${r.lastErrorAr != null ? ' — ${r.lastErrorAr}' : ''}',
          style: styles.bodySmall?.copyWith(color: t.warning),
        ),
        if (next != null && next.isAfter(now))
          Text(
            'المحاولة التالية تلقائيّاً: ${fmtDateTime(next)}',
            style: styles.bodySmall?.copyWith(color: t.muted),
          ),
      ]);
    }
    return Padding(
      padding: const EdgeInsetsDirectional.symmetric(
        horizontal: SahoolSpacing.lg,
        vertical: SahoolSpacing.xs,
      ),
      child: SectionCard(
        key: ValueKey('sync-op-${r.id}'),
        title: outboxTitleAr(r),
        icon: r.isRejected
            ? Icons.error_outline_rounded
            : Icons.schedule_rounded,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            ...lines,
            const SizedBox(height: SahoolSpacing.md),
            Row(
              children: [
                Expanded(
                  child: PrimaryButton(
                    label: r.isRejected ? 'إعادة المحاولة' : 'إرسال الآن',
                    icon: Icons.refresh_rounded,
                    loading: busy,
                    onPressed: online && !busy
                        ? () => context.read<SyncStatusCubit>().retry(r.id)
                        : null,
                  ),
                ),
                const SizedBox(width: SahoolSpacing.sm),
                Expanded(
                  child: SecondaryButton(
                    label: 'تجاهل',
                    icon: Icons.delete_outline_rounded,
                    onPressed: busy ? null : () => _discard(context),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
