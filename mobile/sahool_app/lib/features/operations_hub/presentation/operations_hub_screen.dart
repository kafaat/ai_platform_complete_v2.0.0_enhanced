// SAHOOL — features/operations_hub/presentation/operations_hub_screen.dart
// مركز العمليّات: شبكة وجهات العمل مجمّعة بأقسام — العمليّات أوّلاً (مهام، ريّ،
// مخزون، معدّات، أجهزة …) ثمّ المزرعة وصحّة المحصول والسجلّات. لا يُكتب هنا أيّ
// مسار: الشبكة تُبنى من مداخل MenuEntry في ملفّات مسارات الميزات وتُرشَّح بالدور
// (AppRoute.allowedRoles)، فميزة جديدة تظهر بإضافة `menu:` إلى مسارها. قسم
// الحساب يبقى في «المزيد».
//
// زرّ الرجوع: كان المركز يُخفيه (automaticallyImplyLeading: false) وهو يُفتح
// مدفوعاً من «المزيد»، فيعلق المستخدم بلا سهم رجوع. الآن تلقائيّ: يظهر متى أمكن
// الرجوع.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/routing/app_navigator.dart';
import 'package:sahool_app/core/routing/app_route.dart';
import 'package:sahool_app/core/routing/app_router.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

import '../operations_hub_routes.dart';

/// ترتيب الأقسام في المركز: العمليّات أوّلاً لأنّها غرضه.
const List<MenuSection> kHubSections = [
  MenuSection.operations,
  MenuSection.farm,
  MenuSection.cropHealth,
  MenuSection.records,
];

/// الوجهات الظاهرة لدورٍ في المركز، بالأقسام وترتيبها.
List<MapEntry<MenuSection, List<AppRoute>>> hubGroupsFor(
  AppRouter router,
  AppRole role,
) {
  final menu = router.menuFor(role, sections: kHubSections.toSet());
  return [
    for (final section in kHubSections)
      if (menu[section] != null)
        MapEntry(
          section,
          menu[section]!
              .where((r) => r.path != OperationsHubRoutes.hub)
              .toList(),
        ),
  ].where((e) => e.value.isNotEmpty).toList();
}

class OperationsHubScreen extends StatelessWidget {
  const OperationsHubScreen({super.key, this.router, this.role});

  /// للاختبارات؛ الافتراضيّ الموجِّه والدور الحاليّان.
  final AppRouter? router;
  final AppRole? role;

  @override
  Widget build(BuildContext context) {
    final groups = hubGroupsFor(
      router ?? AppRouter.instance,
      role ?? normalizeRole(currentRole()),
    );
    // ارتفاع البلاطة يتبع حجم الخطّ (1.3× و2×) بدل نسبة ثابتة تفيض.
    final scale = MediaQuery.textScalerOf(context).scale(1);
    final tileHeight = 104 + 36 * scale;
    return AppScaffold(
      title: 'مركز العمليّات',
      body: groups.isEmpty
          ? const EmptyState(
              icon: Icons.grid_off_rounded,
              message: 'لا وحدات تشغيليّة متاحة لدورك.',
            )
          : CustomScrollView(
              slivers: [
                for (final group in groups) ...[
                  SliverToBoxAdapter(
                    child: ListSectionHeader(group.key.labelAr),
                  ),
                  SliverPadding(
                    padding: const EdgeInsetsDirectional.symmetric(
                      horizontal: SahoolSpacing.lg,
                    ),
                    sliver: SliverGrid(
                      gridDelegate: SliverGridDelegateWithMaxCrossAxisExtent(
                        maxCrossAxisExtent: 200,
                        mainAxisExtent: tileHeight,
                        mainAxisSpacing: SahoolSpacing.md,
                        crossAxisSpacing: SahoolSpacing.md,
                      ),
                      delegate: SliverChildBuilderDelegate(
                        (context, i) => HubTile(route: group.value[i]),
                        childCount: group.value.length,
                      ),
                    ),
                  ),
                ],
                const SliverToBoxAdapter(
                  child: SizedBox(height: SahoolSpacing.xl),
                ),
              ],
            ),
    );
  }
}

class HubTile extends StatelessWidget {
  const HubTile({super.key, required this.route});
  final AppRoute route;

  @override
  Widget build(BuildContext context) {
    final primary = context.colors.primary;
    return Semantics(
      button: true,
      label: route.titleAr,
      excludeSemantics: true,
      child: Card(
        key: ValueKey('hub:${route.path}'),
        margin: EdgeInsets.zero,
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: () => context.openRoute<void>(route.path),
          child: Padding(
            padding: const EdgeInsets.all(SahoolSpacing.md),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Container(
                  width: 56,
                  height: 56,
                  decoration: BoxDecoration(
                    color: primary.withValues(alpha: 0.12),
                    shape: BoxShape.circle,
                  ),
                  child: Icon(
                    route.icon ?? Icons.apps_rounded,
                    size: SahoolSizes.iconLg,
                    color: primary,
                  ),
                ),
                const SizedBox(height: SahoolSpacing.sm),
                Flexible(
                  child: Text(
                    route.titleAr,
                    textAlign: TextAlign.center,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: context.textStyles.titleSmall,
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
