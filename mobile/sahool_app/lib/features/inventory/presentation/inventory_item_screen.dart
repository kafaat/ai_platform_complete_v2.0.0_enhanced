// SAHOOL — features/inventory/presentation/inventory_item_screen.dart
// تفاصيل عنصر مخزون: الكمّيّة المتوفّرة وحدّ إعادة الطلب كما حسبهما الخادم،
// الدفعات ذات تاريخ الانتهاء، وإدخال مخزون (دفعة) للمالك/المدير.
//
// حدود الخادم المقيسة (inventory.py:39-183) تُقال ولا تُخفى:
//   • لا نقطة لقراءة عنصر واحد ⇒ التفاصيل تُقرأ من قائمة العناصر (رابط عميق
//     `/inventory/item?item_id=` يعمل بلا حالة مسبقة).
//   • لا نقطة لكلّ الدفعات ⇒ تُعرض الدفعات ذات تاريخ الانتهاء فقط (نافذة 10 سنوات).
//   • لا صرف من المخزون ولا ربط حركة بحقل ⇒ زرّ «صرف» معطّل بسببه المكتوب.
//   • لا بيانات سلامة للمبيدات (فترة التحريم/المادّة الفعّالة) ⇒ تنبيه صادق.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/state_views.dart' show showSnack;
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/inventory/data/inventory_api.dart';
import 'package:sahool_app/features/inventory/data/inventory_models.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';

import 'inventory_screen.dart' show expiryChip, inventoryCategoryIcon;
import 'inventory_sheets.dart';
import 'widgets/inventory_tile.dart';

/// أقصى نافذة يقبلها الخادم لـ/inventory/expiring (le=3650).
const int kAllBatchesWindowDays = 3650;

const String kStockOutUnavailable =
    'الصرف من المخزون وربطه بحقل غير متاحَين بعد في الخادم.';

const String kSafetyDataUnavailable =
    'بيانات السلامة (فترة التحريم قبل الحصاد، فترة منع الدخول، المادّة '
    'الفعّالة) لا يوفّرها الخادم بعد. اقرأ ملصق العبوة والتزم بمعدّات الوقاية '
    'قبل الاستعمال.';

// ── الحالة ──────────────────────────────────────────────────────────

sealed class InventoryItemState {
  const InventoryItemState();
}

class InventoryItemLoading extends InventoryItemState {
  const InventoryItemLoading();
}

class InventoryItemFailed extends InventoryItemState {
  const InventoryItemFailed(this.error);
  final ApiException error;
}

class InventoryItemLoaded extends InventoryItemState {
  const InventoryItemLoaded({required this.item, required this.batches});
  final InventoryItem item;

  /// دفعات هذا العنصر ذات تاريخ انتهاء، الأقرب انتهاءً أوّلاً.
  final List<ExpiringBatch> batches;
}

class InventoryItemCubit extends Cubit<InventoryItemState> {
  InventoryItemCubit(this._api, this.itemId)
    : super(const InventoryItemLoading());

  final InventoryApi _api;
  final String itemId;

  Future<void> load() async {
    if (state is! InventoryItemLoaded) emit(const InventoryItemLoading());
    try {
      final results = await Future.wait<Object>([
        _api.listItems(),
        _api.listExpiring(days: kAllBatchesWindowDays),
      ]);
      if (isClosed) return;
      final items = results[0] as List<InventoryItem>;
      final batches = (results[1] as List<ExpiringBatch>)
          .where((b) => b.itemId == itemId)
          .toList();
      InventoryItem? item;
      for (final i in items) {
        if (i.id == itemId) item = i;
      }
      if (item == null) {
        emit(
          const InventoryItemFailed(
            ApiException(
              kind: ApiErrorKind.notFound,
              statusCode: 404,
              messageAr: 'العنصر غير موجود.',
            ),
          ),
        );
        return;
      }
      emit(InventoryItemLoaded(item: item, batches: batches));
    } catch (e) {
      if (isClosed) return;
      emit(InventoryItemFailed(ApiException.from(e)));
    }
  }
}

// ── الشاشة ──────────────────────────────────────────────────────────

class InventoryItemScreen extends StatelessWidget {
  const InventoryItemScreen({
    super.key,
    required this.itemId,
    this.initial,
    this.api,
    this.role,
    this.outbox,
    this.clock,
  });

  final String itemId;

  /// العنصر من القائمة إن وُجد — عنوان فوريّ بينما تُحمَّل الدفعات.
  final InventoryItem? initial;
  final InventoryApi? api;
  final AppRole? role;
  final OfflineOutbox? outbox;
  final DateTime Function()? clock;

  @override
  Widget build(BuildContext context) {
    final a = api ?? InventoryApi.instance;
    return BlocProvider(
      create: (_) => InventoryItemCubit(a, itemId)..load(),
      child: _ItemView(
        initial: initial,
        api: a,
        role: role ?? normalizeRole(currentRole()),
        outbox: outbox,
        clock: clock ?? DateTime.now,
      ),
    );
  }
}

class _ItemView extends StatefulWidget {
  const _ItemView({
    required this.initial,
    required this.api,
    required this.role,
    required this.outbox,
    required this.clock,
  });

  final InventoryItem? initial;
  final InventoryApi api;
  final AppRole role;
  final OfflineOutbox? outbox;
  final DateTime Function() clock;

  @override
  State<_ItemView> createState() => _ItemViewState();
}

class _ItemViewState extends State<_ItemView> {
  bool _changed = false;

  Future<void> _stockIn(InventoryItem item) async {
    final cubit = context.read<InventoryItemCubit>();
    final result = await showAppBottomSheet<InventoryWriteResult>(
      context,
      builder: (_) => StockInSheet(
        api: widget.api,
        item: item,
        outbox: widget.outbox,
        today: widget.clock(),
      ),
    );
    if (!mounted || result == null) return;
    _changed = true;
    showSnack(context, inventoryResultMessage(result, 'أُضيفت الدفعة'));
    if (result == InventoryWriteResult.saved) await cubit.load();
  }

  @override
  Widget build(BuildContext context) {
    final cubit = context.watch<InventoryItemCubit>();
    final state = cubit.state;
    final title = switch (state) {
      InventoryItemLoaded(:final item) => item.name,
      _ => widget.initial?.name ?? 'عنصر المخزون',
    };
    return PopScope<bool>(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) Navigator.of(context).pop(_changed);
      },
      child: AppScaffold(
        title: title,
        actions: [
          AppIconButton(
            icon: Icons.refresh_rounded,
            tooltip: 'تحديث',
            onPressed: cubit.load,
          ),
        ],
        body: switch (state) {
          InventoryItemLoading() => const LoadingState(),
          InventoryItemFailed(:final error) => ErrorState(
            error: error,
            onRetry: cubit.load,
          ),
          InventoryItemLoaded() => RefreshIndicator(
            onRefresh: cubit.load,
            child: _body(context, state),
          ),
        },
      ),
    );
  }

  Widget _body(BuildContext context, InventoryItemLoaded s) {
    final item = s.item;
    final t = context.tokens;
    final now = widget.clock();
    final manage = canManage(widget.role.name);
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.all(SahoolSpacing.lg),
      children: [
        SectionCard(
          title: item.categoryLabel,
          icon: inventoryCategoryIcon(item.category),
          trailing: item.lowStock
              ? const StatusChip(
                  label: 'مخزون منخفض',
                  tone: StatusTone.danger,
                  icon: Icons.trending_down_rounded,
                )
              : (item.reorderLevel == null
                    ? null
                    : const StatusChip(
                        label: 'كافٍ',
                        tone: StatusTone.success,
                      )),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              MetricTile(
                label: 'الكمّيّة المتوفّرة',
                value: item.totalQuantity,
                unit: item.unit.isEmpty ? null : item.unit,
                decimals: 2,
                icon: Icons.inventory_2_outlined,
              ),
              const SizedBox(height: SahoolSpacing.sm),
              Text(
                item.reorderLevel == null
                    ? 'حدّ إعادة الطلب: غير محدّد — لن يُنبَّه عند الانخفاض.'
                    : 'حدّ إعادة الطلب: '
                          '${fmtNumber(item.reorderLevel, decimals: 2)} ${item.unit}',
                style: context.textStyles.bodyMedium,
              ),
            ],
          ),
        ),
        if (manage) ...[
          const SizedBox(height: SahoolSpacing.lg),
          PrimaryButton(
            label: 'إدخال مخزون (دفعة جديدة)',
            icon: Icons.add_box_outlined,
            onPressed: () => _stockIn(item),
          ),
          const SizedBox(height: SahoolSpacing.sm),
          const SecondaryButton(
            label: 'صرف من المخزون',
            icon: Icons.outbox_outlined,
            onPressed: null,
          ),
          Padding(
            padding: const EdgeInsets.only(top: SahoolSpacing.xs),
            child: Text(
              kStockOutUnavailable,
              style: context.textStyles.bodySmall?.copyWith(color: t.muted),
            ),
          ),
        ],
        if (isAgrochemical(item.category)) ...[
          const SizedBox(height: SahoolSpacing.lg),
          SectionCard(
            title: 'السلامة',
            icon: Icons.health_and_safety_outlined,
            child: Text(
              kSafetyDataUnavailable,
              style: context.textStyles.bodyMedium,
            ),
          ),
        ],
        const SizedBox(height: SahoolSpacing.lg),
        SectionCard(
          title: 'الدفعات ذات تاريخ انتهاء',
          icon: Icons.event_outlined,
          child: s.batches.isEmpty
              ? Text(
                  'لا دفعات بتاريخ انتهاء لهذا العنصر. الخادم لا يعرض بعد '
                  'الدفعات التي بلا تاريخ انتهاء.',
                  style: context.textStyles.bodyMedium?.copyWith(
                    color: t.muted,
                  ),
                )
              : Column(
                  children: [
                    for (final b in s.batches)
                      InventoryTile(
                        key: ValueKey('batch:${b.batchId}'),
                        title: b.quantity == null
                            ? kNotMeasured
                            : '${fmtNumber(b.quantity, decimals: 2)} '
                                  '${b.unit ?? item.unit}',
                        subtitle: 'الانتهاء: ${fmtDate(b.expiryDate)}',
                        chips: [expiryChip(b, now)],
                      ),
                  ],
                ),
        ),
      ],
    );
  }
}
