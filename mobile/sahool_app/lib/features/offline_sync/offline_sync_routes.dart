// SAHOOL — features/offline_sync/offline_sync_routes.dart
// وحدة ميزة «المزامنة دون اتّصال»: صفحة حالة المزامنة (قسم العمليّات في «المزيد»)،
// وتشغيل صندوق الإرسال الدائم عند الإقلاع، وتنظيف الخروج.
//
// تهيئة الوحدة (أوّل وصول إلى [offlineSyncFeature]، أي عند بناء AppRouter في
// main.dart بعد Hive.initFlutter) تبدأ الصندوق المشترك في الخلفيّة كي تُصرَّف
// العمليّات المتبقّية من تشغيلٍ سابق دون انتظار أن تفتح ميزةٌ ما الصندوق.
//
// الخروج لا يحذف عمليّات لم تُرسَل: يوقف التصريف ويُلغي الطلب الجاري، وتبقى
// العمليّات مختومة بمالكها فلا تُرسَل أبداً برمز مستخدم آخر.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_route.dart';

import 'data/durable_offline_outbox.dart';
import 'offline_outbox.dart';
import 'presentation/sync_status_screen.dart';

abstract final class OfflineSyncRoutes {
  static const status = '/offline-sync';
}

final FeatureModule offlineSyncFeature = _buildOfflineSyncFeature();

FeatureModule _buildOfflineSyncFeature() {
  final outbox = OfflineOutbox.instance;
  if (outbox is DurableOfflineOutbox) unawaited(outbox.start());
  return FeatureModule(
    id: 'offline_sync',
    routes: [
      AppRoute(
        path: OfflineSyncRoutes.status,
        titleAr: 'حالة المزامنة',
        icon: Icons.cloud_sync_outlined,
        aliases: const ['/sync-status'],
        menu: const MenuEntry(MenuSection.operations, order: 90),
        builder: (_, _) => const SyncStatusScreen(),
      ),
    ],
    onSessionEnd: (end) async {
      final outbox = OfflineOutbox.instance;
      if (outbox is DurableOfflineOutbox) await outbox.onSessionEnd(end);
    },
  );
}
