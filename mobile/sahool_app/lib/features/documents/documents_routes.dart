// SAHOOL — features/documents/documents_routes.dart
// مسارات ميزة documents. يملكها وكيل هذه الميزة وحده: أضِف شاشاتها هنا، لا في
// app_router.dart ولا في شاشة «المزيد».
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_route.dart';

import 'presentation/documents_screen.dart';

abstract final class DocumentsRoutes {
  static const documents = '/documents';
}

final FeatureModule documentsFeature = FeatureModule(
  id: 'documents',
  routes: [
    AppRoute(
      path: DocumentsRoutes.documents,
      titleAr: 'الوثائق',
      icon: Icons.folder_outlined,
      allowedRoles: RouteRoles.management,
      menu: const MenuEntry(MenuSection.records, order: 20),
      builder: (_, _) => const DocumentsScreen(),
    ),
  ],
);
