// SAHOOL — features/maps/presentation/farm_map_screen.dart
// «خريطة حقولي»: كلّ حقول المستخدم على خريطة واحدة، ملوّنة بحالتها، بتسميات،
// ونقرة على حقل تفتح بطاقته ثمّ مساحة عمله. تعمل مع حزمة الخرائط المحفوظة.
//
// الحالات: تحميل (شريط تقدّم فوق خريطة قابلة للاستعمال)، خطأ (رسالة ApiException
// الصادقة + إعادة محاولة)، فارغ (لا حقول بعد + إضافة لمن يملك الصلاحيّة)، حقول بلا
// حدود مرسومة (تُعدّ صراحةً).
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_map/flutter_map.dart' show TileProvider;
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/routing/app_navigator.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';

import '../data/offline_pack_store.dart';
import 'farm_map_cubit.dart';
import 'layers/fields_layer.dart';
import 'widgets/sahool_map.dart';
import 'widgets/sahool_map_controller.dart';

class FarmMapScreen extends StatelessWidget {
  const FarmMapScreen({
    super.key,
    this.fieldsApi,
    this.packStore,
    this.tileProviderFactory,
    this.canAddField,
  });

  static const routePath = '/maps/farm';

  final FieldsApi? fieldsApi;
  final OfflinePackStore? packStore;

  /// مزوّد بلاطات الأساس (اختبارات)؛ null ⇒ الشبكة.
  final TileProvider Function()? tileProviderFactory;

  /// null ⇒ من دور الجلسة (canMutate).
  final bool? canAddField;

  @override
  Widget build(BuildContext context) => BlocProvider(
    create: (_) => FarmMapCubit(
      fieldsApi ?? FieldsApi.instance,
      packStore ?? OfflinePackStore.instance,
    )..load(),
    child: _FarmMapView(
      tileProviderFactory: tileProviderFactory,
      canAddField: canAddField ?? canMutate(currentRole()),
    ),
  );
}

class _FarmMapView extends StatelessWidget {
  const _FarmMapView({
    required this.tileProviderFactory,
    required this.canAddField,
  });

  final TileProvider Function()? tileProviderFactory;
  final bool canAddField;

  Future<void> _openPacks(BuildContext context) async {
    final cubit = context.read<FarmMapCubit>();
    await context.openRoute<void>('/maps/offline-packs');
    await cubit.refreshOfflinePack();
  }

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      title: 'خريطة حقولي',
      actions: [
        AppIconButton(
          icon: Icons.download_for_offline_outlined,
          tooltip: 'خرائط بلا اتّصال',
          onPressed: () => _openPacks(context),
        ),
        BlocBuilder<FarmMapCubit, FarmMapState>(
          buildWhen: (a, b) => a.status != b.status,
          builder: (context, s) => AppIconButton(
            icon: Icons.refresh,
            tooltip: 'تحديث',
            onPressed: s.status == FarmMapStatus.loading
                ? null
                : () => context.read<FarmMapCubit>().load(),
          ),
        ),
      ],
      body: BlocBuilder<FarmMapCubit, FarmMapState>(
        builder: (context, s) {
          final cubit = context.read<FarmMapCubit>();
          final bounds = fieldsBounds(s.drawable);
          final map = SahoolMap(
            allowRotation: true,
            tileProviderFactory: tileProviderFactory,
            view: bounds == null ? null : MapViewTarget.bounds(bounds),
            offlinePackPath: s.offlinePackPath,
            onTap: cubit.tapAt,
            layers: [FieldsLayer(fields: s.drawable, selectedId: s.selectedId)],
            overlays: [
              if (s.drawable.isNotEmpty)
                PositionedDirectional(
                  bottom: s.selected == null ? 48 : 200,
                  end: SahoolSpacing.sm,
                  child: FieldStatusLegend(
                    statuses: {for (final f in s.drawable) f.status},
                  ),
                ),
            ],
          );
          return Stack(
            children: [
              Positioned.fill(child: map),
              if (s.status == FarmMapStatus.loading)
                const PositionedDirectional(
                  top: 0,
                  start: 0,
                  end: 0,
                  child: LinearProgressIndicator(
                    semanticsLabel: 'جارٍ تحميل الحقول',
                  ),
                ),
              PositionedDirectional(
                start: SahoolSpacing.sm,
                end: SahoolSpacing.sm,
                bottom: SahoolSpacing.xl,
                child: _bottomCard(context, s, cubit),
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _bottomCard(BuildContext context, FarmMapState s, FarmMapCubit cubit) {
    if (s.status == FarmMapStatus.failed) {
      return _Card(
        child: ErrorState(error: s.error!, onRetry: cubit.load),
      );
    }
    if (s.isEmpty) {
      return _Card(
        child: EmptyState(
          icon: Icons.map_outlined,
          title: 'لا حقول بعد',
          message: 'ارسم حدّ حقلك الأوّل ليظهر على الخريطة.',
          actionLabel: canAddField ? 'إضافة حقل' : null,
          onAction: canAddField
              ? () => context.openRoute<void>('/fields/new')
              : null,
        ),
      );
    }
    final selected = s.selected;
    if (selected != null) {
      return _SelectedFieldCard(
        field: selected,
        onClose: () => cubit.select(null),
      );
    }
    if (s.status == FarmMapStatus.loaded && s.withoutGeometry > 0) {
      return _Card(
        child: Padding(
          padding: const EdgeInsetsDirectional.all(SahoolSpacing.md),
          child: Row(
            children: [
              Icon(Icons.info_outline, color: context.tokens.info),
              const SizedBox(width: SahoolSpacing.sm),
              Expanded(
                child: Text(
                  s.drawable.isEmpty
                      ? 'لا حدود مرسومة لأيّ من حقولك (${s.withoutGeometry}) — لا يُرسم ما لا حدّ له.'
                      : '${s.withoutGeometry} من حقولك بلا حدود مرسومة فلا تظهر على الخريطة.',
                  style: context.textStyles.bodyMedium,
                ),
              ),
            ],
          ),
        ),
      );
    }
    return const SizedBox.shrink();
  }
}

class _Card extends StatelessWidget {
  const _Card({required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) => Material(
    elevation: 3,
    color: Theme.of(context).colorScheme.surface,
    borderRadius: SahoolRadius.lgAll,
    child: ConstrainedBox(
      constraints: const BoxConstraints(maxHeight: 320),
      child: child,
    ),
  );
}

StatusTone _tone(FieldMapStatus s) => switch (s) {
  FieldMapStatus.ready => StatusTone.success,
  FieldMapStatus.limited => StatusTone.warning,
  FieldMapStatus.pendingLab => StatusTone.info,
  FieldMapStatus.blocked => StatusTone.danger,
  FieldMapStatus.unknown => StatusTone.neutral,
};

class _SelectedFieldCard extends StatelessWidget {
  const _SelectedFieldCard({required this.field, required this.onClose});
  final MapField field;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    final g = field.geometry;
    return _Card(
      child: Padding(
        padding: const EdgeInsetsDirectional.fromSTEB(
          SahoolSpacing.lg,
          SahoolSpacing.sm,
          SahoolSpacing.xs,
          SahoolSpacing.lg,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    field.name.isEmpty ? 'حقل بلا اسم' : field.name,
                    style: context.textStyles.titleMedium,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                AppIconButton(
                  icon: Icons.close,
                  tooltip: 'إغلاق',
                  onPressed: onClose,
                ),
              ],
            ),
            Padding(
              padding: const EdgeInsetsDirectional.only(end: SahoolSpacing.md),
              child: Wrap(
                spacing: SahoolSpacing.sm,
                runSpacing: SahoolSpacing.xs,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  StatusChip(
                    label: field.status.labelAr,
                    tone: _tone(field.status),
                    icon: field.status.icon,
                  ),
                  Text(
                    'المساحة: ${fmtArea(field.areaHa, decimals: 2)}',
                    style: context.textStyles.bodyMedium,
                  ),
                  if (field.crop != null)
                    Text(
                      'المحصول: ${field.crop}',
                      style: context.textStyles.bodyMedium,
                    ),
                  if (g != null && g.isMulti)
                    Text(
                      '${g.polygons.length} أجزاء',
                      style: context.textStyles.bodyMedium,
                    ),
                ],
              ),
            ),
            const SizedBox(height: SahoolSpacing.md),
            Padding(
              padding: const EdgeInsetsDirectional.only(end: SahoolSpacing.md),
              child: PrimaryButton(
                label: 'فتح مساحة عمل الحقل',
                icon: Icons.dashboard_customize_outlined,
                onPressed: () =>
                    context.openRoute<void>(fieldWorkspaceRoute(field.id)),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
