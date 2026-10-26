// SAHOOL — features/advisor/advisor_routes.dart
// مسارات المستشار الزراعيّ (تبويب «المستشار»)،
// وتنظيف سجلّ المحادثة المشفّر عند الخروج. يملكها وكيل ميزة المستشار.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_route.dart';

import 'advisor_paths.dart';
import 'data/chat_history_store.dart';
import 'presentation/advisor_screen.dart';

export 'advisor_paths.dart';

abstract final class AdvisorRoutes {
  static const advisor = AdvisorPaths.advisor;
}

/// صندوق السجلّ القديم غير المنطَّق (يُفتح في main.dart، يُفرَّغ عند أوّل فتح
/// للمستشار وعند الخروج). السجلّ الحاليّ مشفّر لكلّ مستخدم: chat_history_store.dart.
const String kAdvisorChatBox = kLegacyAdvisorChatBox;

final FeatureModule advisorFeature = FeatureModule(
  id: 'advisor',
  routes: [
    AppRoute(
      path: AdvisorPaths.advisor,
      titleAr: 'المستشار',
      icon: Icons.psychology_outlined,
      builder: (_, args) => AdvisorScreen(
        fieldId: args['field_id'],
        fieldName: args['field_name'],
      ),
    ),
  ],
  // السجلّ المشفّر لهذا المستخدم ومفتاحه يُحذَفان؛ الصندوق القديم يُفرَّغ.
  onSessionEnd: (end) => AdvisorChatStore.instance.endSession(end),
);
