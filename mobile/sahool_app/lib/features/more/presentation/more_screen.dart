// SAHOOL — features/more/presentation/more_screen.dart
// «المزيد»: كلّ الوحدات التي ليست في شريط التنقّل، مجمّعة بأقسام. القائمة لا
// تُكتب هنا: تُبنى من مداخل MenuEntry في ملفّات مسارات الميزات وتُرشَّح بالدور
// (AppRoute.allowedRoles — مثل البيانات المرجعيّة والوثائق للإدارة فقط). ميزة
// جديدة تظهر هنا بإضافة `menu:` إلى مسارها، دون تعديل هذا الملفّ. هذه الشاشة
// تصمّم العرض فقط: رأس الحساب، بطاقة لكلّ قسم بأيقونته، وعناصر بارتفاع ≥56dp.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/routing/app_navigator.dart';
import 'package:sahool_app/core/routing/app_route.dart';
import 'package:sahool_app/core/routing/app_router.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/services/auth_service.dart';

/// مسار الحساب والإعدادات (تملكه ميزة profile) — رأس الشاشة يفتحه.
const String _kProfilePath = '/account/profile';

const Map<AppRole, String> _roleAr = {
  AppRole.owner: 'مالك',
  AppRole.manager: 'مدير',
  AppRole.agronomist: 'مهندس زراعيّ',
  AppRole.worker: 'عامل',
  AppRole.viewer: 'مُشاهِد',
};

IconData _sectionIcon(MenuSection s) => switch (s) {
  MenuSection.farm => Icons.agriculture_outlined,
  MenuSection.cropHealth => Icons.eco_outlined,
  MenuSection.operations => Icons.handyman_outlined,
  MenuSection.records => Icons.folder_copy_outlined,
  MenuSection.account => Icons.manage_accounts_outlined,
};

class MoreScreen extends StatelessWidget {
  const MoreScreen({super.key, this.router, this.role, this.profile});

  /// للاختبارات؛ الافتراضيّ الموجِّه والدور والملفّ الحاليّة.
  final AppRouter? router;
  final AppRole? role;
  final Map<String, dynamic>? profile;

  @override
  Widget build(BuildContext context) {
    final r = router ?? AppRouter.instance;
    final viewerRole = role ?? normalizeRole(currentRole());
    final menu = r.menuFor(viewerRole);
    final p = profile ?? AuthService.instance.userProfile;
    final name = (p?['full_name'] ?? p?['name_ar'])?.toString().trim();
    final profileRoute = r.match(_kProfilePath);
    final canOpenProfile =
        profileRoute != null && profileRoute.allows(viewerRole);
    return AppScaffold(
      title: 'المزيد',
      body: menu.isEmpty
          ? const EmptyState(
              icon: Icons.apps_outlined,
              message: 'لا وحدات إضافيّة متاحة لدورك.',
            )
          : ListView(
              padding: const EdgeInsetsDirectional.only(
                top: SahoolSpacing.sm,
                bottom: SahoolSpacing.xxl,
              ),
              children: [
                _AccountHeader(
                  name: (name == null || name.isEmpty) ? 'حسابي' : name,
                  roleLabel: _roleAr[viewerRole] ?? viewerRole.name,
                  onTap: canOpenProfile
                      ? () => context.openRoute<void>(_kProfilePath)
                      : null,
                ),
                for (final section in menu.entries)
                  _SectionCard(section: section.key, routes: section.value),
              ],
            ),
    );
  }
}

class _AccountHeader extends StatelessWidget {
  const _AccountHeader({
    required this.name,
    required this.roleLabel,
    this.onTap,
  });

  final String name;
  final String roleLabel;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(
      horizontal: SahoolSpacing.lg,
      vertical: SahoolSpacing.sm,
    ),
    child: SectionCard(
      key: const ValueKey('more:account-header'),
      onTap: onTap,
      child: Row(
        children: [
          CircleAvatar(
            radius: 24,
            backgroundColor: context.colors.primary,
            foregroundColor: context.colors.onPrimary,
            child: Text(name.characters.first),
          ),
          const SizedBox(width: SahoolSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  name,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: context.textStyles.titleMedium,
                ),
                Text(
                  roleLabel,
                  style: context.textStyles.bodySmall?.copyWith(
                    color: context.tokens.muted,
                  ),
                ),
              ],
            ),
          ),
          if (onTap != null)
            Icon(Icons.chevron_right_rounded, color: context.tokens.muted),
        ],
      ),
    ),
  );
}

class _SectionCard extends StatelessWidget {
  const _SectionCard({required this.section, required this.routes});
  final MenuSection section;
  final List<AppRoute> routes;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    return Column(
      key: ValueKey('more-section:${section.name}'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(
            SahoolSpacing.lg + SahoolSpacing.xs,
            SahoolSpacing.lg,
            SahoolSpacing.lg,
            SahoolSpacing.sm,
          ),
          child: Semantics(
            header: true,
            child: Row(
              children: [
                Icon(
                  _sectionIcon(section),
                  size: SahoolSizes.iconSm,
                  color: t.muted,
                ),
                const SizedBox(width: SahoolSpacing.sm),
                Text(
                  section.labelAr,
                  style: context.textStyles.titleSmall?.copyWith(
                    color: t.muted,
                  ),
                ),
              ],
            ),
          ),
        ),
        Card(
          margin: const EdgeInsets.symmetric(horizontal: SahoolSpacing.lg),
          clipBehavior: Clip.antiAlias,
          child: Column(
            children: [
              for (var i = 0; i < routes.length; i++) ...[
                if (i > 0)
                  Divider(
                    height: 1,
                    indent: SahoolSpacing.xxl * 2,
                    color: t.line,
                  ),
                AppListTile(
                  key: ValueKey('more:${routes[i].path}'),
                  title: routes[i].titleAr,
                  icon: routes[i].icon ?? Icons.circle_outlined,
                  iconColor: context.colors.primary,
                  onTap: () => context.openRoute<void>(routes[i].path),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

/// للاختبارات والتشخيص: المسارات الظاهرة في «المزيد» لدور.
List<AppRoute> moreRoutesFor(AppRouter router, AppRole role) =>
    router.menuFor(role).values.expand((e) => e).toList();
