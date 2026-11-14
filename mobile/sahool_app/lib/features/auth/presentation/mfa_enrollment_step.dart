// SAHOOL — password-proven MFA enrollment at login (no authenticated session).
// Challenge and activation proof remain in widget memory only; setup is never automatic.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/features/auth/data/auth_api.dart';
import 'widgets/otp_code_field.dart';

enum _EnrollmentStage { intro, setup, done, restart }

class MfaEnrollmentStep extends StatefulWidget {
  const MfaEnrollmentStep({
    super.key,
    required this.api,
    required this.challenge,
    required this.onBackToLogin,
  });

  final AuthApi api;
  final MfaEnrollmentRequiredException challenge;
  final VoidCallback onBackToLogin;

  @override
  State<MfaEnrollmentStep> createState() => _MfaEnrollmentStepState();
}

class _MfaEnrollmentStepState extends State<MfaEnrollmentStep> {
  final _code = TextEditingController();
  _EnrollmentStage _stage = _EnrollmentStage.intro;
  bool _busy = false;
  String? _secret;
  String? _provisioningUri;
  String? _activationProof;
  List<String> _recoveryCodes = <String>[];
  String? _error;

  @override
  void dispose() {
    _clearProofs();
    _code.dispose();
    super.dispose();
  }

  void _clearProofs() {
    _activationProof = null;
    _secret = null;
    _provisioningUri = null;
    _code.clear();
  }

  void _handleError(Object error, {required bool activating}) {
    final status = ApiException.from(error).statusCode;
    if (status == 401 ||
        status == 409 ||
        status == 429 ||
        (!activating && status == 400) ||
        error is FormatException) {
      _clearProofs();
      setState(() {
        _stage = _EnrollmentStage.restart;
        _error = status == 429
            ? 'محاولات كثيرة؛ الحساب مقفل مؤقّتاً. ابدأ الدخول من جديد لاحقاً.'
            : 'انتهت صلاحيّة إثبات MFA أو تغيّرت حالة الحساب. ابدأ الدخول من جديد.';
      });
      return;
    }
    setState(() {
      _error = status == 400 && activating
          ? 'رمز غير صحيح؛ أدخل الرمز الحالي من تطبيق المصادقة.'
          : 'تعذّر إكمال هذه الخطوة؛ تحقّق من الاتصال أو تواصل مع المسؤول.';
    });
  }

  Future<void> _startSetup() async {
    if (_busy || _stage != _EnrollmentStage.intro) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final result = await widget.api.mfaEnrollmentSetup(
        widget.challenge.enrollmentToken,
      );
      if (!mounted) return;
      setState(() {
        _secret = result['secret'] as String;
        _provisioningUri = result['provisioning_uri'] as String;
        _activationProof = result['enrollment_token'] as String;
        _stage = _EnrollmentStage.setup;
      });
    } catch (error) {
      if (mounted) _handleError(error, activating: false);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _activate() async {
    if (_busy || _stage != _EnrollmentStage.setup || _activationProof == null) {
      return;
    }
    final otp = normalizeOtp(_code.text);
    if (otp == null) {
      setState(() => _error = 'أدخل رمز المصادقة المكوّن من 6 أرقام.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final result = await widget.api.mfaEnrollmentActivate(
        _activationProof!,
        otp,
      );
      if (!mounted) return;
      if (result['mfa_enabled'] != true) {
        throw const FormatException('MFA activation result not confirmed');
      }
      final codes = result['recovery_codes'];
      final safeCodes = codes is List
          ? codes.whereType<String>().toList()
          : <String>[];
      _clearProofs();
      setState(() {
        _recoveryCodes = safeCodes;
        _stage = _EnrollmentStage.done;
      });
    } catch (error) {
      if (mounted) _handleError(error, activating: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final done = _stage == _EnrollmentStage.done;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 480),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Icon(Icons.verified_user_outlined, size: 48),
                  const SizedBox(height: 20),
                  Text(
                    'تفعيل المصادقة الثنائيّة',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                  const SizedBox(height: 16),
                  if (_stage == _EnrollmentStage.intro) ...[
                    const Text(
                      'يتطلّب هذا الحساب حماية MFA. اضغط للبدء، ثم أضف السرّ إلى تطبيق المصادقة. لن يتم تسجيل الدخول تلقائيّاً.',
                    ),
                    const SizedBox(height: 16),
                    FilledButton(
                      key: const ValueKey('enroll_start'),
                      onPressed: _busy ? null : _startSetup,
                      child: const Text('بدء إعداد MFA'),
                    ),
                  ],
                  if (_stage == _EnrollmentStage.setup) ...[
                    const Text(
                      'أضف السرّ التالي إلى تطبيق المصادقة. لا تشاركه مع أحد:',
                    ),
                    const SizedBox(height: 8),
                    SelectableText(
                      _secret ?? '',
                      key: const ValueKey('enroll_secret'),
                    ),
                    const SizedBox(height: 10),
                    const Text('رابط إعداد تطبيق المصادقة:'),
                    SelectableText(
                      _provisioningUri ?? '',
                      key: const ValueKey('enroll_uri'),
                    ),
                    const SizedBox(height: 14),
                    OtpCodeField(
                      key: const ValueKey('enroll_code'),
                      controller: _code,
                      enabled: !_busy,
                      autofocus: true,
                      onSubmitted: _activate,
                    ),
                    FilledButton(
                      key: const ValueKey('enroll_activate'),
                      onPressed: _busy ? null : _activate,
                      child: const Text('تأكيد التفعيل'),
                    ),
                  ],
                  if (done) ...[
                    const Text(
                      'تم تفعيل MFA. احفظ رموز الاسترداد الآن؛ لن تظهر مرة أخرى.',
                    ),
                    if (_recoveryCodes.isEmpty)
                      const Text(
                        'لم تُرجع الخدمة رموز استرداد. تواصل مع مسؤول النظام.',
                      ),
                    if (_recoveryCodes.isNotEmpty)
                      SelectableText(
                        _recoveryCodes.join('\n'),
                        key: const ValueKey('enroll_recovery_codes'),
                      ),
                  ],
                  if (_stage == _EnrollmentStage.restart)
                    const Text(
                      'لا يمكن استكمال الإثبات السابق. يلزم إعادة تسجيل الدخول.',
                    ),
                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    Text(
                      _error!,
                      key: const ValueKey('enroll_error'),
                      style: TextStyle(
                        color: Theme.of(context).colorScheme.error,
                      ),
                    ),
                  ],
                  const SizedBox(height: 12),
                  TextButton(
                    key: const ValueKey('enroll_back'),
                    onPressed: _busy ? null : widget.onBackToLogin,
                    child: Text(
                      done
                          ? 'العودة للدخول بالرمز الجديد'
                          : 'العودة إلى تسجيل الدخول',
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
