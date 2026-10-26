// SAHOOL — features/operations_hub/presentation/operations_hub_screen.dart
// مركز العمليّات: شبكة الوحدات التشغيليّة (مهام، ريّ، مخزون، معدّات، أجهزة)
// مبنيّة من مداخل قسم MenuSection.operations في ملفّات مسارات الميزات، مُرشَّحة
// بالدور. لا يُكتب هنا أيّ مسار.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/routing/app_navigator.dart';
import 'package:sahool_app/core/routing/app_route.dart';
import 'package:sahool_app/core/routing/app_router.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/app_states.dart';

import '../operations_hub_routes.dart';

class OperationsHubScreen extends StatelessWidget {
  const OperationsHubScreen({super.key, this.router, this.role});

  final AppRouter? router;
  final AppRole? role;

  @override
  Widget build(BuildContext context) {
    final r = router ?? AppRouter.instance;
    final modules =
        (r.menuFor(
                  role ?? normalizeRole(currentRole()),
                  sections: {MenuSection.operations},
                )[MenuSection.operations] ??
                const <AppRoute>[])
            .where((m) => m.path != OperationsHubRoutes.hub)
            .toList();
    return Scaffold(
      appBar: AppBar(title: const Text('مركز العمليّات')),
      body: modules.isEmpty
          ? const EmptyState(message: 'لا وحدات تشغيليّة متاحة لدورك.')
          : GridView.builder(
              padding: const EdgeInsets.all(SahoolSpacing.lg),
              gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                maxCrossAxisExtent: 220,
                mainAxisSpacing: SahoolSpacing.md,
                crossAxisSpacing: SahoolSpacing.md,
                childAspectRatio: 1.1,
              ),
              itemCount: modules.length,
              itemBuilder: (context, i) {
                final m = modules[i];
                return Card(
                  clipBehavior: Clip.antiAlias,
                  child: InkWell(
                    onTap: () => context.openRoute<void>(m.path),
                    child: Padding(
                      padding: const EdgeInsets.all(SahoolSpacing.md),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(
                            m.icon,
                            size: SahoolSizes.iconLg,
                            color: context.tokens.colors.primary,
                          ),
                          const SizedBox(height: SahoolSpacing.md),
                          Text(
                            m.titleAr,
                            textAlign: TextAlign.center,
                            style: context.textStyles.titleSmall,
                          ),
                        ],
                      ),
                    ),
                  ),
                );
              },
            ),
    );
  }
}
