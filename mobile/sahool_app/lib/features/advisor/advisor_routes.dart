// SAHOOL — features/advisor/advisor_routes.dart
// مسارات المستشار الزراعيّ (تبويب «المستشار»). يملكها وكيل ميزة المستشار، ومعها
// تنظيف سجلّ المحادثة عند الخروج (كان يبقى لمستخدم الجهاز التالي).
import 'package:hive_flutter/hive_flutter.dart';
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_route.dart';

import 'presentation/advisor_screen.dart';

abstract final class AdvisorRoutes {
  static const advisor = '/advisor';
}

/// صندوق سجلّ المحادثة (يُفتح في main.dart).
const String kAdvisorChatBox = 'chat_history';

final FeatureModule advisorFeature = FeatureModule(
  id: 'advisor',
  routes: [
    AppRoute(
      path: AdvisorRoutes.advisor,
      titleAr: 'المستشار',
      icon: Icons.psychology_outlined,
      builder: (_, __) => const AdvisorScreen(),
    ),
  ],
  // السجلّ غير مُنطَّق بالمستخدم وغير مشفّر بعد — أقلّ الواجب مسحه عند الخروج.
  onSessionEnd: (_) async {
    if (Hive.isBoxOpen(kAdvisorChatBox)) {
      await Hive.box<dynamic>(kAdvisorChatBox).clear();
    }
  },
);
