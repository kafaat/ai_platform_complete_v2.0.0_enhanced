// SAHOOL — features/more/presentation/more_screen.dart
// «المزيد»: كلّ الوحدات التي ليست في شريط التنقّل، مجمّعة بأقسام. القائمة لا
// تُكتب هنا: تُبنى من مداخل MenuEntry في ملفّات مسارات الميزات وتُرشَّح بالدور
// (AppRoute.allowedRoles — مثل البيانات المرجعيّة والوثائق للإدارة فقط). ميزة
// جديدة تظهر هنا بإضافة `menu:` إلى مسارها، دون تعديل هذا الملفّ.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/routing/app_navigator.dart';
import 'package:sahool_app/core/routing/app_route.dart';
import 'package:sahool_app/core/routing/app_router.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/widgets/list_tiles.dart';

class MoreScreen extends StatelessWidget {
  const MoreScreen({super.key, this.router, this.role});

  /// للاختبارات؛ الافتراضيّ الموجِّه والدور الحاليّان.
  final AppRouter? router;
  final AppRole? role;

  @override
  Widget build(BuildContext context) {
    final r = router ?? AppRouter.instance;
    final menu = r.menuFor(role ?? normalizeRole(currentRole()));
    return Scaffold(
      appBar: AppBar(
        title: const Text('المزيد'),
        automaticallyImplyLeading: false,
      ),
      body: ListView(
        padding: const EdgeInsetsDirectional.only(bottom: 24),
        children: [
          for (final section in menu.entries) ...[
            ListSectionHeader(section.key.labelAr),
            Card(
              margin: const EdgeInsetsDirectional.symmetric(horizontal: 16),
              child: Column(
                children: [
                  for (final route in section.value)
                    AppListTile(
                      key: ValueKey('more:${route.path}'),
                      title: route.titleAr,
                      icon: route.icon,
                      iconColor: context.tokens.colors.primary,
                      onTap: () => context.openRoute<void>(route.path),
                    ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// للاختبارات والتشخيص: المسارات الظاهرة في «المزيد» لدور.
List<AppRoute> moreRoutesFor(AppRouter router, AppRole role) =>
    router.menuFor(role).values.expand((e) => e).toList();
