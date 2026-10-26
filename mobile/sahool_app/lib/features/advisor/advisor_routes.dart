// SAHOOL — features/advisor/advisor_routes.dart
// مسارات المستشار الزراعيّ (تبويب «المستشار» + توصيات الحقل + تصعيد الآفة)،
// وتنظيف سجلّ المحادثة المشفّر عند الخروج. يملكها وكيل ميزة المستشار.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_route.dart';

import 'advisor_paths.dart';
import 'advisor_permissions.dart';
import 'data/chat_history_store.dart';
import 'presentation/advisor_screen.dart';
import 'presentation/pest_escalation_screen.dart';
import 'presentation/recommendation_detail_screen.dart';
import 'presentation/recommendations_screen.dart';

export 'advisor_paths.dart';

abstract final class AdvisorRoutes {
  static const advisor = AdvisorPaths.advisor;
  static const recommendations = AdvisorPaths.recommendations;
  static const recommendation = AdvisorPaths.recommendation;
  static const pestEscalation = AdvisorPaths.pestEscalation;
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
    AppRoute(
      path: AdvisorPaths.recommendations,
      titleAr: 'توصيات الحقل',
      icon: Icons.fact_check_outlined,
      menu: const MenuEntry(MenuSection.cropHealth, order: 40),
      builder: (_, args) => RecommendationsScreen(fieldId: args['field_id']),
    ),
    AppRoute(
      path: AdvisorPaths.recommendation,
      titleAr: 'تفاصيل التوصية',
      icon: Icons.fact_check_outlined,
      allowedRoles: kRecommendationRequestRoles,
      builder: (_, args) => RecommendationDetailScreen(recId: args['rec_id']),
    ),
    AppRoute(
      path: AdvisorPaths.pestEscalation,
      titleAr: 'تصعيد الآفة',
      icon: Icons.bug_report_outlined,
      allowedRoles: kPestEscalationRoles,
      menu: const MenuEntry(MenuSection.cropHealth, order: 45),
      builder: (_, args) => PestEscalationScreen(fieldId: args['field_id']),
    ),
  ],
  // السجلّ المشفّر لهذا المستخدم ومفتاحه يُحذَفان؛ الصندوق القديم يُفرَّغ.
  onSessionEnd: (end) => AdvisorChatStore.instance.endSession(end),
);
