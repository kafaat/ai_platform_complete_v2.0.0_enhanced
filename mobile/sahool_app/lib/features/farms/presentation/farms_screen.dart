// SAHOOL — features/farms/presentation/farms_screen.dart
// المزارع (أب الحقول): قائمة بعدد حقول كلّ مزرعة، وتفاصيل المزرعة بحقولها.
// الإنشاء للمالك فقط (مطابق للويب والخلفيّة). صدق: المزارع من الخادم فقط،
// التعذّر بحالة خطأ صادقة، والعدد الغائب «غير متاح» لا صفر.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/farms/data/farms_api.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';
import 'package:sahool_app/features/fields/fields_routes.dart';
import 'package:sahool_app/features/fields/presentation/common/field_labels.dart';

import 'farm_form_sheet.dart';
import 'farm_permissions.dart';
import 'farms_cubit.dart';

/// «3 حقول» بصيغة العدد العربيّ.
String fieldsCountAr(int n) => switch (n) {
  0 => 'لا حقول بعد',
  1 => 'حقل واحد',
  2 => 'حقلان',
  <= 10 => '$n حقول',
  _ => '$n حقلاً',
};

class FarmsScreen extends StatelessWidget {
  const FarmsScreen({super.key, this.api, this.fieldsApi, this.role});

  final FarmsApi? api;
  final FieldsApi? fieldsApi;

  /// الدور (للاختبار)؛ افتراضيّاً من الجلسة.
  final AppRole Function()? role;

  @override
  Widget build(BuildContext context) {
    final farmsApi = api ?? FarmsApi.instance;
    return BlocProvider(
      create: (_) =>
          FarmsCubit(farmsApi, fieldsApi ?? FieldsApi.instance)..load(),
      child: _FarmsView(
        api: farmsApi,
        role: (role ?? () => normalizeRole(currentRole()))(),
      ),
    );
  }
}

class _FarmsView extends StatelessWidget {
  const _FarmsView({required this.api, required this.role});

  final FarmsApi api;
  final AppRole role;

  Future<void> _create(BuildContext context) async {
    final cubit = context.read<FarmsCubit>();
    final messenger = ScaffoldMessenger.of(context);
    final created = await showCreateFarmSheet(context, api);
    if (!created) return;
    messenger.showSnackBar(const SnackBar(content: Text('أُنشئت المزرعة')));
    await cubit.load(silent: true);
  }

  @override
  Widget build(BuildContext context) {
    final mayCreate = canCreateFarm(role);
    final state = context.watch<FarmsCubit>().state;
    return Scaffold(
      appBar: AppBar(
        title: const Text('المزارع'),
        actions: [
          AppIconButton(
            icon: Icons.refresh_rounded,
            tooltip: 'تحديث',
            onPressed: () => context.read<FarmsCubit>().load(),
          ),
        ],
      ),
      floatingActionButton: (mayCreate && state is FarmsLoaded)
          ? AppFab(
              key: const ValueKey('create_farm_fab'),
              heroKey: 'farms',
              label: 'مزرعة جديدة',
              icon: Icons.add_rounded,
              onPressed: () => _create(context),
            )
          : null,
      body: switch (state) {
        FarmsLoading() => const LoadingState(message: 'جارٍ تحميل المزارع'),
        FarmsFailed(:final error) => ErrorState(
          error: error,
          onRetry: () => context.read<FarmsCubit>().load(),
        ),
        FarmsLoaded(:final farms) when farms.isEmpty => EmptyState(
          icon: Icons.agriculture_outlined,
          title: 'لا مزارع بعد',
          message: mayCreate
              ? 'أنشئ مزرعتك الأولى لتجمع حقولها تحتها.'
              : 'إنشاء المزارع متاح لمالك الحساب فقط.',
          actionLabel: mayCreate ? 'إنشاء مزرعة' : null,
          onAction: mayCreate ? () => _create(context) : null,
        ),
        FarmsLoaded() => RefreshIndicator(
          onRefresh: () => context.read<FarmsCubit>().load(silent: true),
          child: ListView(
            padding: const EdgeInsetsDirectional.fromSTEB(
              SahoolSpacing.page,
              SahoolSpacing.md,
              SahoolSpacing.page,
              96,
            ),
            children: [
              if (state.countsError != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: SahoolSpacing.sm),
                  child: Text(
                    'عدد الحقول غير متاح: ${state.countsError!.messageAr}',
                    style: context.textStyles.bodySmall,
                  ),
                ),
              for (final f in state.farms)
                _FarmCard(
                  farm: f,
                  count: state.countFor(wText(f['farm_id'], '')),
                  role: role,
                ),
            ],
          ),
        ),
      },
    );
  }
}

class _FarmCard extends StatelessWidget {
  const _FarmCard({
    required this.farm,
    required this.count,
    required this.role,
  });

  final Map<String, dynamic> farm;
  final int? count;
  final AppRole role;

  @override
  Widget build(BuildContext context) {
    final region = wText(farm['region'] ?? farm['location'], '');
    final area = wNum(farm['area_ha']);
    final id = wText(farm['farm_id'], '');
    return Card(
      key: ValueKey('farm_$id'),
      child: InkWell(
        onTap: id.isEmpty
            ? null
            : () => Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => FarmDetailScreen(farm: farm, role: role),
                ),
              ),
        child: Padding(
          padding: const EdgeInsets.all(SahoolSpacing.lg),
          child: Row(
            children: [
              Icon(Icons.agriculture_outlined, color: context.tokens.muted),
              const SizedBox(width: SahoolSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      wText(farm['name']),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: context.textStyles.titleMedium,
                    ),
                    const SizedBox(height: SahoolSpacing.xs),
                    Text(
                      [
                        if (region.isNotEmpty) region,
                        fmtArea(area),
                        count == null
                            ? 'عدد الحقول غير متاح'
                            : fieldsCountAr(count!),
                      ].join(' · '),
                      style: context.textStyles.bodyMedium?.copyWith(
                        color: context.tokens.muted,
                      ),
                    ),
                  ],
                ),
              ),
              Icon(Icons.chevron_right_rounded, color: context.tokens.muted),
            ],
          ),
        ),
      ),
    );
  }
}

/// تفاصيل مزرعة: بياناتها + حقولها (GET /api/v1/farms/{id}/fields).
class FarmDetailScreen extends StatefulWidget {
  const FarmDetailScreen({
    super.key,
    required this.farm,
    required this.role,
    this.api,
  });

  final Map<String, dynamic> farm;
  final AppRole role;
  final FarmsApi? api;

  @override
  State<FarmDetailScreen> createState() => _FarmDetailScreenState();
}

class _FarmDetailScreenState extends State<FarmDetailScreen> {
  late Future<List<Map<String, dynamic>>> _fields = _load();

  Future<List<Map<String, dynamic>>> _load() =>
      (widget.api ?? FarmsApi.instance).listFarmFields(
        wText(widget.farm['farm_id'], ''),
      );

  @override
  Widget build(BuildContext context) {
    final f = widget.farm;
    final created = parseDate(f['created_at']);
    return Scaffold(
      appBar: AppBar(
        title: Text(
          wText(f['name'], 'المزرعة'),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.all(SahoolSpacing.page),
        children: [
          SectionCard(
            title: 'بيانات المزرعة',
            icon: Icons.info_outline_rounded,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _row(context, 'المنطقة', wText(f['region'])),
                _row(context, 'الموقع', wText(f['location'])),
                _row(context, 'المساحة', fmtArea(wNum(f['area_ha']))),
                _row(context, 'تاريخ الإنشاء', fmtDate(created)),
                if (wText(f['description'], '').isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: SahoolSpacing.sm),
                    child: Text(wText(f['description'])),
                  ),
                if (canManage(widget.role.name)) ...[
                  const SizedBox(height: SahoolSpacing.md),
                  Text(
                    'تعديل بيانات المزرعة غير متاح بعد — الخادم لا يوفّر نقطة تعديل للمزارع.',
                    key: const ValueKey('farm_edit_unavailable'),
                    style: context.textStyles.bodySmall,
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(height: SahoolSpacing.md),
          SectionCard(
            title: 'حقول المزرعة',
            icon: Icons.layers_outlined,
            child: FutureBuilder<List<Map<String, dynamic>>>(
              future: _fields,
              builder: (context, snap) {
                if (snap.connectionState != ConnectionState.done) {
                  return const Center(child: CircularProgressIndicator());
                }
                if (snap.hasError) {
                  return ErrorState(
                    error: snap.error!,
                    onRetry: () => setState(() => _fields = _load()),
                  );
                }
                final fields = snap.data!;
                if (fields.isEmpty) {
                  return Text(
                    'لا حقول مرتبطة بهذه المزرعة بعد.',
                    style: context.textStyles.bodyMedium,
                  );
                }
                return Column(
                  children: [
                    for (final fld in fields)
                      AppListTile(
                        icon: Icons.grass_outlined,
                        title: fieldNameOf(fld),
                        subtitle: [
                          ?cropOf(fld),
                          fmtArea(areaOf(fld)),
                        ].join(' · '),
                        onTap: () => Navigator.of(
                          context,
                        ).pushNamed(FieldsRoutes.workspace, arguments: fld),
                      ),
                  ],
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _row(BuildContext context, String label, String value) => Padding(
    padding: const EdgeInsets.symmetric(vertical: SahoolSpacing.xs),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(child: Text(label, style: context.textStyles.bodyMedium)),
        const SizedBox(width: SahoolSpacing.md),
        Flexible(
          child: Text(
            value,
            textAlign: TextAlign.end,
            style: context.textStyles.titleSmall,
          ),
        ),
      ],
    ),
  );
}
