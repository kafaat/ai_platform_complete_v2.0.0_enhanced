// SAHOOL — features/inventory/presentation/inventory_screen.dart
// المخزون: العناصر بمستوى مخزونها، تمييز «منخفض» و«قارب الانتهاء»، بحث وتصفية
// بالفئة، وفتح تفاصيل العنصر. عبر /api/v1/inventory/* (inventory:view للعرض،
// inventory:manage — المالك/المدير فقط — للإضافة). لا بيانات مُلفَّقة: تحميل /
// خطأ صادق / فارغ، والكمّيّات كما حسبها الخادم. تقابل InventoryPage في الويب.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/state_views.dart' show showSnack;
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/inventory/data/inventory_api.dart';
import 'package:sahool_app/features/inventory/data/inventory_models.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';

import 'inventory_cubit.dart';
import 'inventory_item_screen.dart';
import 'inventory_sheets.dart';

IconData inventoryCategoryIcon(String category) => switch (category) {
  'fertilizer' => Icons.grass_outlined,
  'pesticide' => Icons.science_outlined,
  'seed' => Icons.spa_outlined,
  'spare_part' => Icons.build_outlined,
  _ => Icons.inventory_2_outlined,
};

/// «تنتهي خلال N يوم» / «منتهية» كرقاقة حالة (لون + أيقونة + نصّ).
StatusChip expiryChip(ExpiringBatch b, DateTime now) {
  final days = b.daysLeft(now);
  if (days == null) {
    return const StatusChip(label: 'بلا تاريخ', tone: StatusTone.neutral);
  }
  if (days < 0) {
    return const StatusChip(
      label: 'منتهية الصلاحيّة',
      tone: StatusTone.danger,
      icon: Icons.event_busy_outlined,
    );
  }
  if (days == 0) {
    return const StatusChip(
      label: 'تنتهي اليوم',
      tone: StatusTone.danger,
      icon: Icons.event_busy_outlined,
    );
  }
  return StatusChip(
    label: 'تنتهي خلال $days يوم',
    tone: days <= 7 ? StatusTone.danger : StatusTone.warning,
    icon: Icons.event_outlined,
  );
}

class InventoryScreen extends StatelessWidget {
  const InventoryScreen({
    super.key,
    this.api,
    this.role,
    this.outbox,
    this.clock,
  });

  final InventoryApi? api;

  /// للاختبارات؛ الافتراضيّ دور الجلسة.
  final AppRole? role;
  final OfflineOutbox? outbox;
  final DateTime Function()? clock;

  @override
  Widget build(BuildContext context) {
    final a = api ?? InventoryApi.instance;
    return BlocProvider(
      create: (_) => InventoryCubit(a, clock: clock)..load(),
      child: _InventoryView(
        api: a,
        role: role ?? normalizeRole(currentRole()),
        outbox: outbox,
        clock: clock ?? DateTime.now,
      ),
    );
  }
}

class _InventoryView extends StatefulWidget {
  const _InventoryView({
    required this.api,
    required this.role,
    required this.outbox,
    required this.clock,
  });

  final InventoryApi api;
  final AppRole role;
  final OfflineOutbox? outbox;
  final DateTime Function() clock;

  @override
  State<_InventoryView> createState() => _InventoryViewState();
}

class _InventoryViewState extends State<_InventoryView> {
  final _search = TextEditingController();

  // inventory:manage للمالك/المدير فقط (core/authorization.py) — كانت canMutate
  // تُظهر «إضافة» للعامل والمهندس فيرتطمان بـ403.
  bool get _canManage => canManage(widget.role.name);

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _addItem() async {
    final cubit = context.read<InventoryCubit>();
    final result = await showAppBottomSheet<InventoryWriteResult>(
      context,
      builder: (_) => AddInventoryItemSheet(api: widget.api),
    );
    if (!mounted || result == null) return;
    showSnack(context, inventoryResultMessage(result, 'أُضيف عنصر المخزون'));
    await cubit.load();
  }

  Future<void> _openItem(String itemId, InventoryItem? item) async {
    final cubit = context.read<InventoryCubit>();
    final changed = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        settings: const RouteSettings(name: '/inventory/item'),
        builder: (_) => InventoryItemScreen(
          itemId: itemId,
          initial: item,
          api: widget.api,
          role: widget.role,
          outbox: widget.outbox,
          clock: widget.clock,
        ),
      ),
    );
    if (!mounted) return;
    if (changed == true) await cubit.load();
  }

  @override
  Widget build(BuildContext context) {
    final cubit = context.watch<InventoryCubit>();
    final state = cubit.state;
    return AppScaffold(
      title: 'المخزون',
      actions: [
        AppIconButton(
          icon: Icons.refresh_rounded,
          tooltip: 'تحديث',
          onPressed: state is InventoryLoading ? null : cubit.load,
        ),
      ],
      floatingActionButton: _canManage && state is InventoryLoaded
          ? AppFab(
              heroKey: '/inventory',
              label: 'عنصر جديد',
              icon: Icons.add_rounded,
              onPressed: _addItem,
            )
          : null,
      body: switch (state) {
        InventoryLoading() => const LoadingState(
          message: 'جارٍ تحميل المخزون…',
        ),
        InventoryFailed(:final error) => ErrorState(
          error: error,
          onRetry: cubit.load,
        ),
        InventoryLoaded() => RefreshIndicator(
          onRefresh: cubit.load,
          child: _buildLoaded(context, cubit, state),
        ),
      },
    );
  }

  Widget _buildLoaded(
    BuildContext context,
    InventoryCubit cubit,
    InventoryLoaded s,
  ) {
    final now = widget.clock();
    if (s.items.isEmpty && s.expiring.isEmpty) {
      return CustomScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: [
          if (s.refreshError != null)
            SliverToBoxAdapter(
              child: OpsRefreshBanner(
                error: s.refreshError!,
                fetchedAt: s.fetchedAt,
                now: now,
              ),
            ),
          SliverFillRemaining(
            child: EmptyState(
              icon: Icons.inventory_2_outlined,
              title: 'لا توجد عناصر مخزون بعد',
              message: _canManage
                  ? 'سجّل الأسمدة والمبيدات والبذور وقطع الغيار لتتبّع كمّيّاتها '
                        'وصلاحيّتها.'
                  : 'لم يسجّل المالك أو المدير أيّ عنصر بعد.',
              actionLabel: _canManage ? 'أضف أوّل عنصر' : null,
              onAction: _canManage ? _addItem : null,
            ),
          ),
        ],
      );
    }
    final visible = s.visibleItems;
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      // حشوة سفليّة كي لا يغطّي الزرّ العائم آخر عنصر.
      padding: const EdgeInsetsDirectional.only(bottom: 96),
      children: [
        if (s.refreshError != null)
          OpsRefreshBanner(
            error: s.refreshError!,
            fetchedAt: s.fetchedAt,
            now: now,
          ),
        _Summary(state: s),
        if (s.expiring.isNotEmpty) ...[
          const ListSectionHeader(
            'دفعات تنتهي خلال $kExpiringWindowDays يوماً',
          ),
          for (final b in s.expiring)
            _ExpiringTile(
              batch: b,
              now: now,
              onTap: () => _openItem(b.itemId, _findItem(s, b.itemId)),
            ),
        ],
        const ListSectionHeader('العناصر'),
        _Filters(
          state: s,
          search: _search,
          onQuery: cubit.setQuery,
          onCategory: cubit.setCategory,
          onLowOnly: cubit.setLowOnly,
        ),
        if (visible.isEmpty)
          Padding(
            padding: const EdgeInsets.all(SahoolSpacing.xl),
            child: Column(
              children: [
                Text(
                  s.items.isEmpty
                      ? 'لا عناصر مسجّلة.'
                      : 'لا عناصر تطابق التصفية.',
                  textAlign: TextAlign.center,
                  style: context.textStyles.bodyLarge?.copyWith(
                    color: context.tokens.muted,
                  ),
                ),
                if (s.isFiltered) ...[
                  const SizedBox(height: SahoolSpacing.md),
                  SecondaryButton(
                    label: 'مسح التصفية',
                    expand: false,
                    onPressed: () {
                      _search.clear();
                      cubit.clearFilters();
                    },
                  ),
                ],
              ],
            ),
          )
        else
          for (final item in visible)
            _ItemTile(item: item, onTap: () => _openItem(item.id, item)),
      ],
    );
  }

  InventoryItem? _findItem(InventoryLoaded s, String id) {
    for (final i in s.items) {
      if (i.id == id) return i;
    }
    return null;
  }
}

class _Summary extends StatelessWidget {
  const _Summary({required this.state});
  final InventoryLoaded state;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsetsDirectional.fromSTEB(
      SahoolSpacing.md,
      SahoolSpacing.md,
      SahoolSpacing.md,
      0,
    ),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: MetricTile(
            label: 'العناصر',
            value: state.items.length,
            decimals: 0,
            icon: Icons.inventory_2_outlined,
          ),
        ),
        Expanded(
          child: MetricTile(
            label: 'مخزون منخفض',
            value: state.lowStockCount,
            decimals: 0,
            icon: Icons.trending_down_rounded,
          ),
        ),
        Expanded(
          child: MetricTile(
            label: 'دفعات قاربت الانتهاء',
            value: state.expiring.length,
            decimals: 0,
            icon: Icons.event_outlined,
          ),
        ),
      ],
    ),
  );
}

class _Filters extends StatelessWidget {
  const _Filters({
    required this.state,
    required this.search,
    required this.onQuery,
    required this.onCategory,
    required this.onLowOnly,
  });

  final InventoryLoaded state;
  final TextEditingController search;
  final ValueChanged<String> onQuery;
  final ValueChanged<String?> onCategory;
  final ValueChanged<bool> onLowOnly;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Padding(
        padding: const EdgeInsetsDirectional.symmetric(
          horizontal: SahoolSpacing.lg,
        ),
        child: TextField(
          controller: search,
          onChanged: onQuery,
          textInputAction: TextInputAction.search,
          decoration: const InputDecoration(
            hintText: 'ابحث باسم العنصر',
            prefixIcon: Icon(Icons.search_rounded),
          ),
        ),
      ),
      SizedBox(
        height: SahoolSizes.minTouchTarget + SahoolSpacing.md,
        child: ListView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsetsDirectional.symmetric(
            horizontal: SahoolSpacing.lg,
            vertical: SahoolSpacing.xs,
          ),
          children: [
            FilterChip(
              label: const Text('منخفض فقط'),
              avatar: const Icon(
                Icons.trending_down_rounded,
                size: SahoolSizes.iconSm,
              ),
              selected: state.lowOnly,
              onSelected: onLowOnly,
            ),
            const SizedBox(width: SahoolSpacing.sm),
            ChoiceChip(
              label: const Text('الكلّ'),
              selected: state.category == null,
              onSelected: (_) => onCategory(null),
            ),
            for (final e in kInventoryCategories.entries) ...[
              const SizedBox(width: SahoolSpacing.sm),
              ChoiceChip(
                label: Text(e.value),
                selected: state.category == e.key,
                onSelected: (sel) => onCategory(sel ? e.key : null),
              ),
            ],
          ],
        ),
      ),
    ],
  );
}

class _ExpiringTile extends StatelessWidget {
  const _ExpiringTile({
    required this.batch,
    required this.now,
    required this.onTap,
  });

  final ExpiringBatch batch;
  final DateTime now;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final expired = batch.isExpired(now);
    final qty = batch.quantity == null
        ? kNotMeasured
        : '${fmtNumber(batch.quantity, decimals: 2)} ${batch.unit ?? ''}'
              .trim();
    return Card(
      margin: const EdgeInsetsDirectional.symmetric(
        horizontal: SahoolSpacing.lg,
        vertical: SahoolSpacing.xs,
      ),
      child: OpsTile(
        key: ValueKey('expiring:${batch.batchId}'),
        title: batch.name.isEmpty ? '—' : batch.name,
        subtitle: 'الكمّيّة: $qty · الانتهاء: ${fmtDate(batch.expiryDate)}',
        icon: expired ? Icons.event_busy_outlined : Icons.event_outlined,
        iconColor: expired ? t.danger : t.warning,
        chips: [expiryChip(batch, now)],
        onTap: onTap,
      ),
    );
  }
}

class _ItemTile extends StatelessWidget {
  const _ItemTile({required this.item, required this.onTap});
  final InventoryItem item;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final qty = item.totalQuantity == null
        ? kNotMeasured
        : '${fmtNumber(item.totalQuantity, decimals: 2)} ${item.unit}'.trim();
    final reorder = item.reorderLevel == null
        ? ''
        : ' · حدّ الطلب ${fmtNumber(item.reorderLevel, decimals: 2)}';
    return Card(
      margin: const EdgeInsetsDirectional.symmetric(
        horizontal: SahoolSpacing.lg,
        vertical: SahoolSpacing.xs,
      ),
      child: OpsTile(
        key: ValueKey('item:${item.id}'),
        title: item.name.isEmpty ? '—' : item.name,
        subtitle: '${item.categoryLabel} · المتوفّر: $qty$reorder',
        icon: inventoryCategoryIcon(item.category),
        iconColor: item.lowStock ? t.danger : context.colors.primary,
        chips: [
          if (item.lowStock)
            const StatusChip(
              label: 'مخزون منخفض',
              tone: StatusTone.danger,
              icon: Icons.trending_down_rounded,
            ),
        ],
        onTap: onTap,
      ),
    );
  }
}
