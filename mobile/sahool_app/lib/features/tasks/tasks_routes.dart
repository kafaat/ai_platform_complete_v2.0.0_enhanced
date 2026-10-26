// SAHOOL — features/tasks/tasks_routes.dart
// مسارات المهام (تبويب «المهام» في الغلاف، ومُدرَجة في قسم العمليّات لمن لا
// يظهر له التبويب). يملكها وكيل ميزة المهام وحده.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_route.dart';

import 'presentation/tasks_screen.dart';

abstract final class TasksRoutes {
  static const tasks = '/tasks';
}

final FeatureModule tasksFeature = FeatureModule(
  id: 'tasks',
  routes: [
    AppRoute(
      path: TasksRoutes.tasks,
      titleAr: 'المهام',
      icon: Icons.task_alt_outlined,
      menu: const MenuEntry(MenuSection.operations, order: 10),
      builder: (_, __) => const TasksScreen(),
    ),
  ],
);
