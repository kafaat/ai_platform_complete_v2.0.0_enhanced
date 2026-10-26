// SAHOOL — features/auth/presentation/login_screen.dart
// شاشة الدخول. تنادي POST /auth/login عبر AuthApi، تحفظ التوكن في التخزين الآمن،
// ثمّ تُعلِم AuthGate عبر AuthState. صدق: كلّ فشل يُعرض بسببه الحقيقيّ (بيانات
// خاطئة ≠ انقطاع ≠ مهلة ≠ خادم معطّل) — لا «حدث خطأ» عامّ ولا جلسة زائفة.
// حقول كبيرة (هدف لمس ≥48dp، خطّ 16)، إظهار/إخفاء كلمة المرور، ورمز MFA يقبل
// الأرقام العربيّة-الهنديّة.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/routing/app_navigator.dart';
import 'package:sahool_app/core/session/auth_state.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/auth/data/auth_api.dart';

import 'widgets/otp_code_field.dart';

/// رسالة فشل الدخول بلغة المستخدم، مشتقّة من نوع الفشل المقيس.
String loginErrorMessage(Object error, {bool mfaStep = false}) {
  if (error is MfaRequiredException) return 'أدخل رمز المصادقة الثنائيّة.';
  final e = ApiException.from(error);
  switch (e.kind) {
    case ApiErrorKind.unauthorized:
      return mfaStep
          ? 'رمز التحقّق غير صحيح أو انتهت صلاحيّته. أدخل الرمز الحاليّ من التطبيق.'
          : 'البريد الإلكترونيّ أو كلمة المرور غير صحيحة.';
    case ApiErrorKind.forbidden:
      return 'هذا الحساب غير مسموح له بالدخول. تواصل مع مسؤول المزرعة.';
    case ApiErrorKind.timeout:
      return 'انتهت مهلة الاتصال بالخادم. الشبكة ضعيفة — حاول مجدّداً بعد قليل.';
    case ApiErrorKind.network:
      return 'لا يوجد اتصال بالخادم. تحقّق من الإنترنت ثمّ حاول مجدّداً.';
    case ApiErrorKind.rateLimited:
      return 'محاولات كثيرة. انتظر دقيقة ثمّ حاول مجدّداً.';
    case ApiErrorKind.unavailable:
      return 'خدمة الدخول غير متاحة حاليّاً على الخادم. حاول لاحقاً.';
    case ApiErrorKind.server:
      return 'الخادم يواجه مشكلة الآن (${e.statusCode}). حاول لاحقاً.';
    case ApiErrorKind.validation:
    case ApiErrorKind.badRequest:
      return 'تحقّق من صيغة البريد الإلكترونيّ وكلمة المرور.';
    case ApiErrorKind.cancelled:
      return 'أُلغي الطلب.';
    default:
      return e.messageAr;
  }
}

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, this.api});

  /// للاختبارات؛ الافتراضيّ AuthApi.instance.
  final AuthApi? api;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _mfaCode = TextEditingController();
  final _passwordFocus = FocusNode();
  bool _loading = false;
  bool _obscure = true;
  String? _error;
  bool _errorIsConnectivity = false;
  // كُشِف حقل MFA بعد أن أعاد الخادم X-MFA-Required لهذه البيانات. عند ظهوره
  // يتحوّل الزرّ الرئيسيّ من «تسجيل الدخول» إلى «تحقّق» (يعيد النداء مع الرمز).
  bool _mfaRequired = false;

  AuthApi get _api => widget.api ?? AuthApi.instance;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _mfaCode.dispose();
    _passwordFocus.dispose();
    super.dispose();
  }

  void _setError(Object e, {bool mfaStep = false}) {
    if (!mounted) return;
    setState(() {
      _error = loginErrorMessage(e, mfaStep: mfaStep);
      _errorIsConnectivity = ApiException.from(e).isConnectivity;
    });
  }

  Future<void> _submit() async {
    if (_loading) return;
    if (_mfaRequired) return _verifyMfa();
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await _api.login(_email.text.trim(), _password.text);
      _onLoginSuccess();
    } on MfaRequiredException {
      // كلمة المرور صحّت لكن يلزم رمز TOTP ⇒ اكشف الحقل بدل إعلان فشل.
      if (mounted) {
        setState(() {
          _mfaRequired = true;
          _error = null;
        });
      }
    } catch (e) {
      _setError(e);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  /// إعادة النداء مع رمز MFA. رمز خاطئ ⇒ 401 يُعرض سطريّاً دون إخفاء الحقل.
  Future<void> _verifyMfa() async {
    if (_loading) return;
    final code = normalizeOtp(_mfaCode.text);
    if (code == null) {
      setState(() {
        _error = 'أدخل رمز المصادقة المكوّن من 6 أرقام.';
        _errorIsConnectivity = false;
      });
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await _api.login(_email.text.trim(), _password.text, mfaCode: code);
      _onLoginSuccess();
    } on MfaRequiredException {
      // الخادم ما زال يطلب الرمز (سباق نادر) ⇒ أبقِ الحقل واطلب إعادة الإدخال.
      _setError(
        const ApiException(kind: ApiErrorKind.unauthorized, messageAr: ''),
        mfaStep: true,
      );
    } catch (e) {
      _setError(e, mfaStep: true);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _backToCredentials() {
    setState(() {
      _mfaRequired = false;
      _mfaCode.clear();
      _error = null;
    });
  }

  void _onLoginSuccess() {
    if (!mounted) return;
    // AuthGate يستمع إلى AuthState: التوكن محفوظ ⇒ يوصِل WebSocket ويعرض الغلاف.
    // إن فُتحت الشاشة مدفوعةً (/login بعد انتهاء الجلسة) نعود إلى الجذر.
    AuthState.instance.signedIn();
    context.popToRoot();
  }

  Future<void> _forgotPassword() async {
    await showAppBottomSheet<void>(
      context,
      builder: (_) =>
          _ResetPasswordSheet(api: _api, initialEmail: _email.text.trim()),
    );
  }

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final styles = context.textStyles;
    final fieldStyle = styles.bodyLarge;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(SahoolSpacing.xl),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 480),
              child: AutofillGroup(
                child: Form(
                  key: _formKey,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      ExcludeSemantics(
                        child: Icon(
                          Icons.eco_rounded,
                          size: 64,
                          color: context.colors.primary,
                        ),
                      ),
                      const SizedBox(height: SahoolSpacing.md),
                      Text(
                        'سهول',
                        textAlign: TextAlign.center,
                        style: styles.headlineMedium?.copyWith(
                          fontWeight: SahoolType.bold,
                        ),
                      ),
                      const SizedBox(height: SahoolSpacing.xs),
                      Text(
                        'المنصّة الزراعيّة الذكيّة',
                        textAlign: TextAlign.center,
                        style: styles.bodyMedium?.copyWith(color: t.muted),
                      ),
                      const SizedBox(height: SahoolSpacing.xxl),
                      if (!_mfaRequired) ...[
                        TextFormField(
                          key: const ValueKey('login_email'),
                          controller: _email,
                          enabled: !_loading,
                          keyboardType: TextInputType.emailAddress,
                          textInputAction: TextInputAction.next,
                          textDirection: TextDirection.ltr,
                          autofillHints: const [
                            AutofillHints.email,
                            AutofillHints.username,
                          ],
                          style: fieldStyle,
                          decoration: const InputDecoration(
                            labelText: 'البريد الإلكترونيّ',
                            prefixIcon: Icon(Icons.email_outlined),
                          ),
                          onFieldSubmitted: (_) =>
                              _passwordFocus.requestFocus(),
                          validator: (v) {
                            final s = v?.trim() ?? '';
                            if (s.isEmpty) return 'أدخل بريدك الإلكترونيّ';
                            if (!s.contains('@') || !s.contains('.')) {
                              return 'أدخل بريداً صحيحاً مثل name@example.com';
                            }
                            return null;
                          },
                        ),
                        const SizedBox(height: SahoolSpacing.lg),
                        TextFormField(
                          key: const ValueKey('login_password'),
                          controller: _password,
                          focusNode: _passwordFocus,
                          enabled: !_loading,
                          obscureText: _obscure,
                          textInputAction: TextInputAction.done,
                          autofillHints: const [AutofillHints.password],
                          style: fieldStyle,
                          decoration: InputDecoration(
                            labelText: 'كلمة المرور',
                            prefixIcon: const Icon(Icons.lock_outline),
                            suffixIcon: AppIconButton(
                              key: const ValueKey('login_toggle_password'),
                              icon: _obscure
                                  ? Icons.visibility_outlined
                                  : Icons.visibility_off_outlined,
                              tooltip: _obscure
                                  ? 'إظهار كلمة المرور'
                                  : 'إخفاء كلمة المرور',
                              onPressed: () =>
                                  setState(() => _obscure = !_obscure),
                            ),
                          ),
                          onFieldSubmitted: (_) => _submit(),
                          validator: (v) => (v == null || v.isEmpty)
                              ? 'أدخل كلمة المرور'
                              : null,
                        ),
                      ] else ...[
                        Text(
                          'حسابك محميّ بالمصادقة الثنائيّة. افتح تطبيق المصادقة '
                          'وأدخل الرمز الظاهر الآن.',
                          textAlign: TextAlign.center,
                          style: styles.bodyLarge,
                        ),
                        const SizedBox(height: SahoolSpacing.lg),
                        OtpCodeField(
                          key: const ValueKey('login_mfa_code'),
                          controller: _mfaCode,
                          autofocus: true,
                          enabled: !_loading,
                          onSubmitted: _verifyMfa,
                        ),
                      ],
                      if (_error != null) ...[
                        const SizedBox(height: SahoolSpacing.lg),
                        _ErrorNote(
                          message: _error!,
                          connectivity: _errorIsConnectivity,
                        ),
                      ],
                      const SizedBox(height: SahoolSpacing.xl),
                      PrimaryButton(
                        key: const ValueKey('login_submit'),
                        label: _mfaRequired ? 'تحقّق ودخول' : 'تسجيل الدخول',
                        icon: _mfaRequired
                            ? Icons.verified_user_outlined
                            : Icons.login_rounded,
                        loading: _loading,
                        onPressed: _submit,
                      ),
                      const SizedBox(height: SahoolSpacing.sm),
                      if (_mfaRequired)
                        TextButton(
                          onPressed: _loading ? null : _backToCredentials,
                          child: const Text('رجوع لتغيير الحساب'),
                        )
                      else
                        TextButton(
                          key: const ValueKey('login_forgot'),
                          onPressed: _loading ? null : _forgotPassword,
                          child: const Text('نسيت كلمة المرور؟'),
                        ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _ErrorNote extends StatelessWidget {
  const _ErrorNote({required this.message, required this.connectivity});
  final String message;
  final bool connectivity;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final color = connectivity ? t.warning : t.danger;
    return Semantics(
      liveRegion: true,
      child: Container(
        key: const ValueKey('login_error'),
        padding: const EdgeInsets.all(SahoolSpacing.md),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.10),
          borderRadius: SahoolRadius.mdAll,
          border: Border.all(color: color),
        ),
        child: Row(
          children: [
            Icon(
              connectivity
                  ? Icons.wifi_off_rounded
                  : Icons.error_outline_rounded,
              color: color,
            ),
            const SizedBox(width: SahoolSpacing.sm),
            Expanded(
              child: Text(message, style: context.textStyles.bodyMedium),
            ),
          ],
        ),
      ),
    );
  }
}

/// طلب رابط استعادة كلمة المرور. الردّ لا يكشف هل البريد مسجّل.
class _ResetPasswordSheet extends StatefulWidget {
  const _ResetPasswordSheet({required this.api, required this.initialEmail});
  final AuthApi api;
  final String initialEmail;

  @override
  State<_ResetPasswordSheet> createState() => _ResetPasswordSheetState();
}

class _ResetPasswordSheetState extends State<_ResetPasswordSheet> {
  late final TextEditingController _email = TextEditingController(
    text: widget.initialEmail,
  );
  bool _sending = false;
  bool _sent = false;
  String? _error;

  @override
  void dispose() {
    _email.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final email = _email.text.trim();
    if (!email.contains('@')) {
      setState(() => _error = 'أدخل بريداً صحيحاً.');
      return;
    }
    setState(() {
      _sending = true;
      _error = null;
    });
    try {
      await widget.api.requestPasswordReset(email);
      if (mounted) setState(() => _sent = true);
    } catch (e) {
      if (mounted) setState(() => _error = loginErrorMessage(e));
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_sent) {
      return AppSheet(
        title: 'تحقّق من بريدك',
        submitLabel: 'تمّ',
        onSubmit: () => Navigator.of(context).pop(),
        children: const [
          SizedBox(height: SahoolSpacing.md),
          Text(
            'إن كان البريد مسجّلاً لدينا فستصلك رسالة برابط لتعيين كلمة مرور '
            'جديدة.',
          ),
        ],
      );
    }
    return AppSheet(
      title: 'استعادة كلمة المرور',
      submitLabel: 'إرسال الرابط',
      submitting: _sending,
      errorText: _error,
      onSubmit: _send,
      children: [
        const SizedBox(height: SahoolSpacing.md),
        AppTextField(
          label: 'البريد الإلكترونيّ',
          controller: _email,
          keyboardType: TextInputType.emailAddress,
          prefixIcon: Icons.email_outlined,
        ),
      ],
    );
  }
}
