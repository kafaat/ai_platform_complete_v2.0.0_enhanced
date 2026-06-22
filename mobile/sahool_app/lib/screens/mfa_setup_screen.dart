// SAHOOL — lib/screens/mfa_setup_screen.dart
// شاشة تفعيل/تعطيل المصادقة الثنائيّة (MFA / TOTP — RFC 6238).
// تدفّق التفعيل (يطابق frontend/src SettingsPage.AccountSecurity والعقد في
// services/auth/main.py):
//   1) «بدء التفعيل» ⇒ POST /auth/mfa/setup ⇒ يُعيد secret + provisioning_uri.
//   2) نعرض رمز QR (otpauth://) + السرّ نصّاً للإدخال اليدويّ. يُعرَض مرّة واحدة.
//   3) المستخدم يُدخل الرمز من تطبيق المصادقة ⇒ POST /auth/mfa/activate ⇒ تفعيل.
//   4) تعطيل: POST /auth/mfa/disable برمز صحيح حاليّاً.
// صدق تامّ: لا نجاح زائف — كلّ فشل يُعرَض بالعربيّة عبر apiErrorMessage. السرّ
// يُعرَض مرّة واحدة فقط (لا نُعيد جلبه ولا نخزّنه). RTL عالميّ مضمون من main.dart.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart'
    show Clipboard, ClipboardData, FilteringTextInputFormatter;
import 'package:qr_flutter/qr_flutter.dart';

import '../services/api_service.dart';
import '../widgets/state_views.dart';

const _kField = Color(0xFF1A1D29);
const _kBorder = Color(0xFF334155);
const _kDanger = Color(0xFFF87171);
const _kMuted = Color(0xFF94A3B8);

class MfaSetupScreen extends StatefulWidget {
  const MfaSetupScreen({super.key});

  @override
  State<MfaSetupScreen> createState() => _MfaSetupScreenState();
}

class _MfaSetupScreenState extends State<MfaSetupScreen> {
  // setupData != null ⇒ بدأ الاقتران (نعرض السرّ + QR) بانتظار التفعيل.
  String? _secret;
  String? _provisioningUri;
  bool _activated = false; // فُعِّل MFA في هذه الجلسة ⇒ نخفي السرّ ونعرض نجاحاً.
  bool _disabledOk = false;

  final _activateCode = TextEditingController();
  final _disableCode = TextEditingController();

  bool _busy = false; // عمليّة setup/activate جارية.
  bool _disableBusy = false;
  bool _showDisable = false;

  String? _error; // خطأ مسار التفعيل.
  String? _disableError; // خطأ مسار التعطيل.

  @override
  void dispose() {
    _activateCode.dispose();
    _disableCode.dispose();
    super.dispose();
  }

  Future<void> _startSetup() async {
    setState(() {
      _busy = true;
      _error = null;
      _activated = false;
      _disabledOk = false;
    });
    try {
      final data = await ApiService.instance.mfaSetup();
      final secret = data['secret'] as String?;
      final uri = data['provisioning_uri'] as String?;
      if (secret == null || uri == null) {
        throw const FormatException('استجابة الخادم بلا سرّ/رابط اقتران');
      }
      if (mounted) {
        setState(() {
          _secret = secret;
          _provisioningUri = uri;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(
            () => _error = _humanize(e, 'تعذّر بدء اقتران المصادقة الثنائيّة'));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _activate() async {
    final code = _activateCode.text.trim();
    if (code.length != 6) {
      setState(() => _error = 'أدخل الرمز المكوّن من 6 أرقام من تطبيق المصادقة');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ApiService.instance.mfaActivate(code);
      if (mounted) {
        setState(() {
          _activated = true;
          // السرّ يُعرَض مرّة واحدة فقط — نخفيه بعد التفعيل الناجح.
          _secret = null;
          _provisioningUri = null;
          _activateCode.clear();
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() =>
            _error = _humanize(e, 'رمز غير صحيح — تأكّد من تطبيق المصادقة'));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _disable() async {
    final code = _disableCode.text.trim();
    if (code.length != 6) {
      setState(
          () => _disableError = 'أدخل الرمز الحاليّ (6 أرقام) لتأكيد التعطيل');
      return;
    }
    setState(() {
      _disableBusy = true;
      _disableError = null;
    });
    try {
      await ApiService.instance.mfaDisable(code);
      if (mounted) {
        setState(() {
          _disabledOk = true;
          _showDisable = false;
          _disableCode.clear();
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() =>
            _disableError = _humanize(e, 'تعذّر تعطيل المصادقة الثنائيّة'));
      }
    } finally {
      if (mounted) setState(() => _disableBusy = false);
    }
  }

  // رسالة صادقة: نُفضّل تفصيل الخادم (`detail`) إن وُجد، وإلّا apiErrorMessage.
  String _humanize(Object e, String fallback) {
    final msg = apiErrorMessage(e);
    return msg.isNotEmpty ? msg : fallback;
  }

  Future<void> _copySecret() async {
    final s = _secret;
    if (s == null) return;
    await Clipboard.setData(ClipboardData(text: s));
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('نُسخ السرّ')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: kBg,
      appBar: AppBar(
        backgroundColor: kSurface,
        title: const Text('المصادقة الثنائيّة (MFA)'),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text(
                'طبقة حماية إضافيّة: عند الدخول يُطلَب رمز مؤقّت من تطبيق مصادقة '
                '(Google Authenticator / Authy).',
                style: TextStyle(color: _kMuted, fontSize: 13, height: 1.5),
              ),
              const SizedBox(height: 20),

              if (_activated) _okBox('تم تفعيل المصادقة الثنائيّة بنجاح'),
              if (_disabledOk) _okBox('تم تعطيل المصادقة الثنائيّة'),

              // ── بدء الاقتران ──────────────────────────────────────
              if (_secret == null && !_activated)
                ElevatedButton.icon(
                  onPressed: _busy ? null : _startSetup,
                  icon: _busy
                      ? const SizedBox(
                          height: 18,
                          width: 18,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: Colors.white))
                      : const Icon(Icons.shield_outlined),
                  label: const Text('بدء تفعيل المصادقة الثنائيّة'),
                  style: _btnStyle(kPrimary),
                ),

              // ── عرض السرّ + QR + رمز التفعيل ──────────────────────
              if (_secret != null) ...[
                _setupCard(),
                const SizedBox(height: 16),
                const Text('رمز التأكيد (من تطبيق المصادقة)',
                    style: TextStyle(color: Colors.white, fontSize: 13)),
                const SizedBox(height: 8),
                _codeField(
                  controller: _activateCode,
                  onSubmitted: () {
                    if (!_busy) _activate();
                  },
                ),
                const SizedBox(height: 16),
                ElevatedButton.icon(
                  onPressed: _busy ? null : _activate,
                  icon: _busy
                      ? const SizedBox(
                          height: 18,
                          width: 18,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: Colors.white))
                      : const Icon(Icons.check_circle_outline),
                  label: const Text('تفعيل'),
                  style: _btnStyle(kPrimary),
                ),
              ],

              if (_error != null) ...[
                const SizedBox(height: 14),
                Text(_error!,
                    style: const TextStyle(color: _kDanger, fontSize: 13)),
              ],

              // ── تعطيل MFA ────────────────────────────────────────
              const SizedBox(height: 28),
              const Divider(color: _kBorder),
              const SizedBox(height: 12),
              if (!_showDisable)
                Align(
                  alignment: AlignmentDirectional.centerStart,
                  child: TextButton(
                    onPressed: () => setState(() {
                      _showDisable = true;
                      _disableError = null;
                      _disabledOk = false;
                    }),
                    child: const Text(
                      'تعطيل المصادقة الثنائيّة (إن كانت مفعّلة)',
                      style: TextStyle(color: _kMuted, fontSize: 13),
                    ),
                  ),
                )
              else ...[
                const Text('أدخل رمزاً صحيحاً حاليّاً لتأكيد التعطيل.',
                    style: TextStyle(color: _kMuted, fontSize: 13)),
                const SizedBox(height: 10),
                _codeField(
                  controller: _disableCode,
                  onSubmitted: () {
                    if (!_disableBusy) _disable();
                  },
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: ElevatedButton(
                        onPressed: _disableBusy ? null : _disable,
                        style: _btnStyle(const Color(0xFFDC2626)),
                        child: _disableBusy
                            ? const SizedBox(
                                height: 18,
                                width: 18,
                                child: CircularProgressIndicator(
                                    strokeWidth: 2, color: Colors.white))
                            : const Text('تعطيل'),
                      ),
                    ),
                    const SizedBox(width: 10),
                    TextButton(
                      onPressed: _disableBusy
                          ? null
                          : () => setState(() => _showDisable = false),
                      child: const Text('إلغاء',
                          style: TextStyle(color: _kMuted)),
                    ),
                  ],
                ),
                if (_disableError != null) ...[
                  const SizedBox(height: 12),
                  Text(_disableError!,
                      style: const TextStyle(color: _kDanger, fontSize: 13)),
                ],
              ],
            ],
          ),
        ),
      ),
    );
  }

  // بطاقة الاقتران: QR (otpauth://) + السرّ نصّاً للإدخال اليدويّ.
  Widget _setupCard() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: kSurface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: _kBorder),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text(
            'امسح رمز QR في تطبيق المصادقة، أو أدخل السرّ يدويّاً. '
            'يُعرَض مرّة واحدة فقط.',
            style: TextStyle(color: _kMuted, fontSize: 12, height: 1.5),
          ),
          const SizedBox(height: 16),
          Center(
            child: Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(10),
              ),
              child: QrImageView(
                data: _provisioningUri!,
                size: 200,
                backgroundColor: Colors.white,
              ),
            ),
          ),
          const SizedBox(height: 16),
          const Text('السرّ (للإدخال اليدويّ):',
              style: TextStyle(color: _kMuted, fontSize: 12)),
          const SizedBox(height: 6),
          Row(
            children: [
              Expanded(
                child: SelectableText(
                  _secret!,
                  textDirection: TextDirection.ltr,
                  style: const TextStyle(
                    color: kPrimary,
                    fontSize: 14,
                    fontFamily: 'monospace',
                    letterSpacing: 1.2,
                  ),
                ),
              ),
              IconButton(
                onPressed: _copySecret,
                icon: const Icon(Icons.copy, color: _kMuted, size: 20),
                tooltip: 'نسخ',
              ),
            ],
          ),
        ],
      ),
    );
  }

  // حقل رمز TOTP موحّد: 6 أرقام، لوحة أرقام، مُتمركز بتباعد واضح.
  Widget _codeField({
    required TextEditingController controller,
    required VoidCallback onSubmitted,
  }) {
    return TextField(
      controller: controller,
      keyboardType: TextInputType.number,
      maxLength: 6,
      textAlign: TextAlign.center,
      textDirection: TextDirection.ltr,
      inputFormatters: [FilteringTextInputFormatter.digitsOnly],
      style: const TextStyle(
          color: Colors.white, fontSize: 22, letterSpacing: 8),
      onSubmitted: (_) => onSubmitted(),
      decoration: InputDecoration(
        counterText: '',
        hintText: '______',
        hintStyle: const TextStyle(color: _kMuted, letterSpacing: 8),
        prefixIcon: const Icon(Icons.shield_outlined, color: _kMuted),
        filled: true,
        fillColor: _kField,
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: _kBorder),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: kPrimary),
        ),
      ),
    );
  }

  Widget _okBox(String msg) => Container(
        margin: const EdgeInsets.only(bottom: 16),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: kPrimary.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: kPrimary),
        ),
        child: Row(
          children: [
            const Icon(Icons.check_circle_outline, color: kPrimary, size: 20),
            const SizedBox(width: 8),
            Expanded(
              child: Text(msg,
                  style: const TextStyle(color: kPrimary, fontSize: 13)),
            ),
          ],
        ),
      );

  ButtonStyle _btnStyle(Color bg) => ElevatedButton.styleFrom(
        backgroundColor: bg,
        foregroundColor: Colors.white,
        padding: const EdgeInsets.symmetric(vertical: 14),
        shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12)),
      );
}
