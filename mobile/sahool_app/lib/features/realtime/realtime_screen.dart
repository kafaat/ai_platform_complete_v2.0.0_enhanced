import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:sahool_app/core/theme/tokens.dart';

import '../../services/api_service.dart';
import '../../services/auth_service.dart';
import 'livekit_transport.dart';
import 'realtime_api.dart';
import 'realtime_controller.dart';

const realtimeCallsEnabled = bool.fromEnvironment(
  'SAHOOL_REALTIME_CALL_ENABLED',
);
bool get nativeRealtimeCallsEnabled =>
    realtimeCallsEnabled &&
    !kIsWeb &&
    (defaultTargetPlatform == TargetPlatform.android ||
        defaultTargetPlatform == TargetPlatform.iOS);

class RealtimeScreen extends StatefulWidget {
  const RealtimeScreen({required this.fieldId, super.key, this.controller});
  final String fieldId;

  /// للاختبارات: متحكّم جاهز بنقل وهميّ (المكالمات الحقيقيّة خلف علم بناء).
  @visibleForTesting
  final RealtimeController? controller;

  @override
  State<RealtimeScreen> createState() => _RealtimeScreenState();
}

class _RealtimeScreenState extends State<RealtimeScreen>
    with WidgetsBindingObserver {
  RealtimeController? _controller;
  bool _consent = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    final injected = widget.controller;
    if (injected != null) {
      _controller = injected..addListener(_refresh);
    } else if (nativeRealtimeCallsEnabled &&
        AuthService.instance.isAuthenticated &&
        widget.fieldId.isNotEmpty) {
      _controller = RealtimeController(
        fieldId: widget.fieldId,
        api: RealtimeApi(ApiService.instance.dio),
        transport: LiveKitTransport(),
      )..addListener(_refresh);
    }
  }

  void _refresh() {
    if (mounted) setState(() {});
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final controller = _controller;
    if (controller != null) {
      unawaited(controller.setForeground(state == AppLifecycleState.resumed));
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _controller?.removeListener(_refresh);
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = _controller;
    return Scaffold(
      appBar: AppBar(title: const Text('استشارة صوتية للحقل')),
      // قابل للتمرير: نصّ الموافقة طويل، فكان العمود يفيض على الهواتف الصغيرة
      // أو مع تكبير الخطّ فتختفي الموافقة وزرّ الاتصال.
      body: controller == null
          ? const Center(
              child: Padding(
                padding: EdgeInsets.all(SahoolSpacing.xl),
                child: Text(
                  'المكالمات غير مفعّلة أو تتطلب تسجيل الدخول.',
                  textAlign: TextAlign.center,
                ),
              ),
            )
          : SafeArea(
              top: false,
              child: ListView(
                key: const ValueKey('realtime_body'),
                padding: const EdgeInsets.all(SahoolSpacing.lg),
                children: [
                  const Text(
                    'استشارة صوتية للقراءة فقط. لا تُنفّذ أوامر الري أو المعدات.',
                  ),
                  const SizedBox(height: SahoolSpacing.lg),
                  const Text(
                    'يُرسل صوتك إلى خدمة التفريغ الصوتي. قد تُحفظ الأسئلة والنصائح ضمن سجل تدقيق الذكاء الاصطناعي الحالي في سهول. لا تُفعّل الكاميرا. تنتهي الجلسة عند مغادرة التطبيق أو هذه الصفحة.',
                  ),
                  CheckboxListTile(
                    value: _consent,
                    onChanged: controller.phase == RealtimePhase.idle
                        ? (value) {
                            setState(() {
                              _consent = value ?? false;
                            });
                          }
                        : null,
                    title: const Text(
                      'أوافق على المعالجة الصوتية وسجل التدقيق الموضّح.',
                    ),
                  ),
                  if (controller.phase == RealtimePhase.idle)
                    FilledButton(
                      onPressed: _consent
                          ? () {
                              unawaited(controller.join(consent: _consent));
                            }
                          : null,
                      child: const Text('إنشاء الجلسة والاتصال صامتًا'),
                    ),
                  if (controller.phase == RealtimePhase.joining)
                    const LinearProgressIndicator(),
                  if (controller.phase == RealtimePhase.muted ||
                      controller.phase == RealtimePhase.speaking)
                    FilledButton(
                      onPressed: controller.phase == RealtimePhase.speaking
                          ? () {
                              unawaited(controller.mute());
                            }
                          : controller.canEnable
                          ? () {
                              unawaited(controller.enableMicrophone());
                            }
                          : null,
                      child: Text(
                        controller.phase == RealtimePhase.speaking
                            ? 'إيقاف الميكروفون'
                            : 'السماح للميكروفون والتحدث',
                      ),
                    ),
                  if (controller.message != null) Text(controller.message!),
                  if (controller.phase == RealtimePhase.ended)
                    const Text('انتهت الجلسة. ارجع إلى الحقل لبدء جلسة جديدة.'),
                  if (controller.phase != RealtimePhase.idle &&
                      controller.phase != RealtimePhase.ended)
                    TextButton(
                      onPressed: () {
                        unawaited(controller.leave());
                      },
                      child: const Text('إنهاء الجلسة'),
                    ),
                ],
              ),
            ),
    );
  }
}
