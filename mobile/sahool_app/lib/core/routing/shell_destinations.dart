// SAHOOL — lib/core/routing/shell_destinations.dart
// وجهات شريط التنقّل السفليّ. خمس على الأكثر (Material)، وكلّ وجهة تشير إلى
// مسار تملكه ميزة (يُبنى محتوى التبويب من AppRoute.builder لتلك الميزة).
//
// منطق الأدوار (ممارسة التطبيقات الزراعيّة: العامل الميدانيّ يبدأ يومه بمهامه):
//   • owner/manager/agronomist: الرئيسية · الحقول · المهام · المستشار · المزيد.
//   • worker: الوجهات نفسها، والتبويب الافتتاحيّ «المهام».
//   • viewer (قراءة فقط): بلا «المهام» — لا ينفّذ مهامّ؛ تبقى المهام متاحة
//     للقراءة من «المزيد ← العمليّات».
// الخادم يفرض الصلاحيّات على كلّ نقطة؛ هذا تنظيم واجهة فقط.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/permissions/permissions.dart';

@immutable
class ShellDestination {
  const ShellDestination({
    required this.id,
    required this.labelAr,
    required this.icon,
    required this.selectedIcon,
    required this.routePath,
    this.roles,
  });

  final String id;
  final String labelAr;
  final IconData icon;
  final IconData selectedIcon;

  /// المسار القانونيّ للميزة التي يعرضها التبويب.
  final String routePath;

  /// null ⇒ لكلّ الأدوار.
  final Set<AppRole>? roles;

  bool visibleFor(AppRole role) => roles == null || roles!.contains(role);
}

const List<ShellDestination> kShellDestinations = [
  ShellDestination(
    id: 'home',
    labelAr: 'الرئيسية',
    icon: Icons.home_outlined,
    selectedIcon: Icons.home_rounded,
    routePath: '/dashboard',
  ),
  ShellDestination(
    id: 'fields',
    labelAr: 'الحقول',
    icon: Icons.layers_outlined,
    selectedIcon: Icons.layers_rounded,
    routePath: '/fields',
  ),
  ShellDestination(
    id: 'tasks',
    labelAr: 'المهام',
    icon: Icons.task_alt_outlined,
    selectedIcon: Icons.task_alt_rounded,
    routePath: '/tasks',
    roles: {AppRole.owner, AppRole.manager, AppRole.agronomist, AppRole.worker},
  ),
  ShellDestination(
    id: 'advisor',
    labelAr: 'المستشار',
    icon: Icons.psychology_outlined,
    selectedIcon: Icons.psychology_rounded,
    routePath: '/advisor',
  ),
  ShellDestination(
    id: 'more',
    labelAr: 'المزيد',
    icon: Icons.menu_rounded,
    selectedIcon: Icons.menu_open_rounded,
    routePath: '/more',
  ),
];

List<ShellDestination> destinationsFor(AppRole role,
        [List<ShellDestination> all = kShellDestinations]) =>
    all.where((d) => d.visibleFor(role)).toList(growable: false);

/// معرّف التبويب الافتتاحيّ للدور.
String initialDestinationFor(AppRole role) =>
    role == AppRole.worker ? 'tasks' : 'home';
