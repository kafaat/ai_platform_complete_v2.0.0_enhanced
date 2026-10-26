// SAHOOL — features/tasks/tasks_routes.dart
// مسارات المهام (تبويب «المهام» في الغلاف، ومُدرَجة في قسم العمليّات لمن لا
// يظهر له التبويب). يملكها وكيل ميزة المهام وحده.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/routing/app_route.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/services/auth_service.dart';

import 'presentation/task_detail_screen.dart';
import 'presentation/tasks_cubit.dart';
import 'presentation/tasks_screen.dart';

abstract final class TasksRoutes {
  static const tasks = '/tasks';

  /// `/tasks/detail?task_id=<id>` — رابط عميق لمهمّة (من إشعار مثلاً).
  static const detail = '/tasks/detail';
}

final FeatureModule tasksFeature = FeatureModule(
  id: 'tasks',
  routes: [
    AppRoute(
      path: TasksRoutes.tasks,
      titleAr: 'المهام',
      icon: Icons.task_alt_outlined,
      menu: const MenuEntry(MenuSection.operations, order: 10),
      builder: (_, _) => const TasksScreen(),
    ),
    AppRoute(
      path: TasksRoutes.detail,
      titleAr: 'تفاصيل المهمّة',
      icon: Icons.assignment_outlined,
      builder: (_, args) {
        final id = args['task_id'];
        if (id == null || id.isEmpty) {
          return const AppScaffold(
            title: 'تفاصيل المهمّة',
            body: EmptyState(
              title: 'لم تُحدَّد مهمّة',
              message: 'الرابط لا يحمل معرّف مهمّة (task_id).',
              icon: Icons.link_off_rounded,
            ),
          );
        }
        return BlocProvider<TasksCubit>(
          create: (_) =>
              TasksCubit(userId: AuthService.instance.userId)..load(),
          child: TaskDetailScreen(
            taskId: id,
            canEdit: canMutate(currentRole()),
            photos: TaskPhotoTools.standard,
          ),
        );
      },
    ),
  ],
);
