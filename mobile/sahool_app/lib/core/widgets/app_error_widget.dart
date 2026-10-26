// SAHOOL — lib/core/widgets/app_error_widget.dart
// بديل ErrorWidget عند فشل بناء ودجة. مضغوط وليس Scaffold (كان يرسم شاشة كاملة
// بزرّ «إعادة التشغيل» داخل عنصر قائمة). التفاصيل في وضع التطوير فقط.
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

class AppErrorWidget extends StatelessWidget {
  const AppErrorWidget({super.key, required this.details, required this.message});

  final FlutterErrorDetails details;

  /// الرسالة الآمنة للإنتاج.
  final String message;

  @override
  Widget build(BuildContext context) => Directionality(
        textDirection: TextDirection.rtl,
        child: Container(
          color: const Color(0x14C0392B),
          padding: const EdgeInsets.all(12),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, color: Color(0xFFC0392B), size: 20),
              const SizedBox(width: 8),
              Flexible(
                child: Text(
                  kDebugMode ? details.exceptionAsString() : message,
                  maxLines: 4,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: Color(0xFFC0392B), fontSize: 12),
                ),
              ),
            ],
          ),
        ),
      );
}
