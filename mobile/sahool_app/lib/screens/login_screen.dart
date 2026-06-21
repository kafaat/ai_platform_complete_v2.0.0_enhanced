// SAHOOL — lib/screens/login_screen.dart
// شاشة دخول حقيقيّة (كانت placeholder). تنادي POST /auth/login عبر ApiService،
// تحفظ التوكن في التخزين الآمن، ثمّ تعيد بناء AuthGate (يوصِل WebSocket ويعرض
// الواجهة). صدق: الفشل يُعرَض للمستخدم بالعربيّة، لا جلسة زائفة.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show FilteringTextInputFormatter;
import '../main.dart';
import '../services/api_service.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _mfaCode = TextEditingController();
  bool _loading = false;
  bool _obscure = true;
  String? _error;
  // كُشِف حقل MFA بعد أن أعاد الخادم X-MFA-Required لهذه البيانات. عند ظهوره
  // يتحوّل الزرّ الرئيسيّ من «تسجيل الدخول» إلى «تحقّق» (يعيد النداء مع الرمز).
  bool _mfaRequired = false;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _mfaCode.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    // إن كان حقل MFA مكشوفاً، الإرسال يساوي «تحقّق» (لا تكرار للمنطق).
    if (_mfaRequired) return _verifyMfa();
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await ApiService.instance.login(_email.text.trim(), _password.text);
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
      if (mounted) setState(() => _error = _humanize(e));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  /// إعادة النداء مع رمز MFA. رمز خاطئ ⇒ 401 «رمز MFA غير صحيح» يُعرَض سطريّاً
  /// دون إخفاء الحقل (يصحّح المستخدم رمزه ويعيد المحاولة).
  Future<void> _verifyMfa() async {
    final code = _mfaCode.text.trim();
    if (code.length != 6) {
      setState(() => _error = 'أدخل رمز المصادقة المكوّن من 6 أرقام');
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await ApiService.instance
          .login(_email.text.trim(), _password.text, mfaCode: code);
      _onLoginSuccess();
    } on MfaRequiredException {
      // الخادم ما زال يطلب الرمز (سباق نادر) ⇒ أبقِ الحقل واطلب إعادة الإدخال.
      if (mounted) setState(() => _error = 'رمز MFA غير صحيح');
    } catch (e) {
      if (mounted) {
        setState(() => _error =
            e.toString().contains('401') ? 'رمز MFA غير صحيح' : _humanize(e));
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _onLoginSuccess() {
    if (!mounted) return;
    // إعادة بناء AuthGate: التوكن محفوظ ⇒ يوصِل WebSocket ويعرض MainNavigation.
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const AuthGate()),
      (route) => false,
    );
  }

  String _humanize(Object e) {
    final s = e.toString();
    if (s.contains('401') || s.contains('403')) {
      return 'بيانات الدخول غير صحيحة';
    }
    if (s.contains('SocketException') || s.contains('connection')) {
      return 'تعذّر الاتّصال بالخادم — تحقّق من الشبكة';
    }
    return 'تعذّر تسجيل الدخول، حاول مجدّداً';
  }

  @override
  Widget build(BuildContext context) {
    const green = Color(0xFF10B981);
    return Scaffold(
      backgroundColor: const Color(0xFF0F1117),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Form(
              key: _formKey,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text('🌿', style: TextStyle(fontSize: 56),
                      textAlign: TextAlign.center),
                  const SizedBox(height: 12),
                  const Text('سهول',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                          color: Colors.white,
                          fontSize: 26,
                          fontWeight: FontWeight.bold)),
                  const SizedBox(height: 4),
                  const Text('المنصّة الزراعيّة الذكيّة',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: Colors.grey, fontSize: 13)),
                  const SizedBox(height: 32),
                  TextFormField(
                    controller: _email,
                    keyboardType: TextInputType.emailAddress,
                    style: const TextStyle(color: Colors.white),
                    decoration: _dec('البريد الإلكترونيّ', Icons.email_outlined),
                    validator: (v) => (v == null || !v.contains('@'))
                        ? 'أدخل بريداً صحيحاً'
                        : null,
                  ),
                  const SizedBox(height: 14),
                  TextFormField(
                    controller: _password,
                    obscureText: _obscure,
                    style: const TextStyle(color: Colors.white),
                    decoration: _dec('كلمة المرور', Icons.lock_outline).copyWith(
                      suffixIcon: IconButton(
                        icon: Icon(
                            _obscure ? Icons.visibility_off : Icons.visibility,
                            color: Colors.grey),
                        onPressed: () => setState(() => _obscure = !_obscure),
                      ),
                    ),
                    validator: (v) => (v == null || v.length < 6)
                        ? 'كلمة المرور قصيرة جدّاً'
                        : null,
                  ),
                  // حقل رمز MFA (TOTP) — يُكشَف فقط بعد أن يطلبه الخادم. 6 أرقام،
                  // لوحة أرقام، يُرسَل بزرّ «تحقّق» (onSubmitted) أو الزرّ الرئيسيّ.
                  if (_mfaRequired) ...[
                    const SizedBox(height: 14),
                    const Text('أدخل رمز المصادقة الثنائيّة (MFA)',
                        textAlign: TextAlign.center,
                        style: TextStyle(color: Colors.grey, fontSize: 13)),
                    const SizedBox(height: 8),
                    TextField(
                      controller: _mfaCode,
                      autofocus: true,
                      keyboardType: TextInputType.number,
                      maxLength: 6,
                      textAlign: TextAlign.center,
                      inputFormatters: [
                        FilteringTextInputFormatter.digitsOnly,
                      ],
                      style: const TextStyle(
                          color: Colors.white,
                          fontSize: 22,
                          letterSpacing: 8),
                      decoration: _dec('______', Icons.shield_outlined)
                          .copyWith(counterText: ''),
                      onSubmitted: (_) {
                        if (!_loading) _verifyMfa();
                      },
                    ),
                  ],
                  if (_error != null) ...[
                    const SizedBox(height: 14),
                    Text(_error!,
                        textAlign: TextAlign.center,
                        style: const TextStyle(
                            color: Color(0xFFF87171), fontSize: 13)),
                  ],
                  const SizedBox(height: 24),
                  ElevatedButton(
                    onPressed: _loading ? null : _submit,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: green,
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12)),
                    ),
                    child: _loading
                        ? const SizedBox(
                            height: 20,
                            width: 20,
                            child: CircularProgressIndicator(
                                strokeWidth: 2, color: Colors.white))
                        : Text(_mfaRequired ? 'تحقّق' : 'تسجيل الدخول',
                            style: const TextStyle(
                                color: Colors.white,
                                fontSize: 16,
                                fontWeight: FontWeight.bold)),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  InputDecoration _dec(String label, IconData icon) => InputDecoration(
        labelText: label,
        labelStyle: const TextStyle(color: Colors.grey),
        prefixIcon: Icon(icon, color: Colors.grey),
        filled: true,
        fillColor: const Color(0xFF1A1D29),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Color(0xFF334155)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Color(0xFF10B981)),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Color(0xFFF87171)),
        ),
      );
}
