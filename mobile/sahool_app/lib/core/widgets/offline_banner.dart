// SAHOOL — lib/core/widgets/offline_banner.dart
// لافتة «لا اتّصال بالشبكة» على مستوى التطبيق. تُركَّب مرّة واحدة في
// MaterialApp.builder فتظهر فوق كلّ الشاشات (المدفوعة أيضاً)، وتُزيل الحشوة
// العلويّة من المحتوى حين تظهر كي لا يُضاعَف شريط الحالة.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/network/connectivity_status.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';

class OfflineBannerHost extends StatelessWidget {
  const OfflineBannerHost({super.key, required this.child, this.status});

  final Widget child;

  /// يُحقَن في الاختبارات؛ الافتراضيّ حالة التطبيق.
  final ConnectivityStatus? status;

  @override
  Widget build(BuildContext context) {
    final s = status ?? ConnectivityStatus.instance;
    return ValueListenableBuilder<bool>(
      valueListenable: s,
      builder: (context, online, _) {
        if (online) return child;
        return Column(
          children: [
            const OfflineBanner(),
            Expanded(
              child: MediaQuery.removePadding(
                  context: context, removeTop: true, child: child),
            ),
          ],
        );
      },
    );
  }
}

class OfflineBanner extends StatelessWidget {
  const OfflineBanner({super.key});

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    return Material(
      color: t.warning,
      child: SafeArea(
        bottom: false,
        child: Semantics(
          liveRegion: true,
          child: Padding(
            padding: const EdgeInsetsDirectional.symmetric(
                horizontal: SahoolSpacing.lg, vertical: SahoolSpacing.sm),
            child: Row(
              children: [
                Icon(Icons.wifi_off_rounded,
                    size: SahoolSizes.iconSm, color: t.background),
                const SizedBox(width: SahoolSpacing.sm),
                Expanded(
                  child: Text(
                    'لا اتّصال بالشبكة — ما يُعرَض قد لا يكون محدَّثاً، والإرسال سيفشل حتّى يعود الاتّصال.',
                    style: TextStyle(
                        color: t.background,
                        fontSize: SahoolType.caption,
                        fontWeight: SahoolType.semibold),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
