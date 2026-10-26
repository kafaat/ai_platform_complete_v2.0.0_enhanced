// SAHOOL — features/auth/presentation/mfa_setup_screen.dart
// شاشة تفعيل/تعطيل المصادقة الثنائيّة (MFA / TOTP — RFC 6238).
// تدفّق التفعيل (يطابق frontend/src SettingsPage.AccountSecurity والعقد في
// services/auth/main.py):
//   1) «بدء التفعيل» ⇒ POST /auth/mfa/setup ⇒ يُعيد secret + provisioning_uri.
//   2) نعرض رمز QR (otpauth://) + السرّ نصّاً للإدخال اليدويّ. يُعرَض مرّة واحدة.
//   3) المستخدم يُدخل الرمز من تطبيق المصادقة ⇒ POST /auth/mfa/activate ⇒ تفعيل.
//   4) تعطيل: POST /auth/mfa/disable برمز صحيح حاليّاً.
// صدق تامّ: لا نجاح زائف — كلّ فشل يُعرَض بالعربيّة. السرّ يُعرَض مرّة واحدة فقط
// (لا نُعيد جلبه ولا نخزّنه). الرمز يقبل الأرقام العربيّة-الهنديّة (كان
// digitsOnly يحذفها فلا يُكتب الرمز من لوحة عربيّة)، والتعطيل يُؤكَّد صراحةً.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show Clipboard, ClipboardData;
import 'package:qr_flutter/qr_flutter.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/auth/data/auth_api.dart';

import 'widgets/otp_code_field.dart';

class MfaSetupScreen extends StatefulWidget {
  const MfaSetupScreen({super.key, this.api});

  /// للاختبارات؛ الافتراضيّ AuthApi.instance.
  final AuthApi? api;

  @override
  State<MfaSetupScreen> createState() => _MfaSetupScreenState();
}

class _MfaSetupScreenState extends State<MfaSetupScreen> {
  AuthApi get _api => widget.api ?? AuthApi.instance;

  // _secret != null ⇒ بدأ الاقتران (نعرض السرّ + QR) بانتظار التفعيل.
  String? _secret;
  String? _provisioningUri;
  bool _activated = false; // فُعِّل في هذه الجلسة ⇒ نخفي السرّ ونعرض نجاحاً.
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

  /// رسالة صادقة: تفصيل الخادم (400 «رمز غير صحيح»/«مفعّل سلفاً») إن وُجد.
  String _humanize(Object e, String fallback) {
    final err = ApiException.from(e);
    if (err.kind == ApiErrorKind.badRequest) {
      final d = err.detail;
      return d is String && d.isNotEmpty ? d : fallback;
    }
    return err.messageAr.isNotEmpty ? err.messageAr : fallback;
  }

  Future<void> _startSetup() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
      _activated = false;
      _disabledOk = false;
    });
    try {
      final data = await _api.mfaSetup();
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
          () => _error = _humanize(e, 'تعذّر بدء اقتران المصادقة الثنائيّة'),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _activate() async {
    if (_busy) return;
    final code = normalizeOtp(_activateCode.text);
    if (code == null) {
      setState(
        () => _error = 'أدخل الرمز المكوّن من 6 أرقام من تطبيق المصادقة',
      );
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await _api.mfaActivate(code);
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
        setState(
          () => _error = _humanize(e, 'رمز غير صحيح — تأكّد من تطبيق المصادقة'),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _disable() async {
    if (_disableBusy) return;
    final code = normalizeOtp(_disableCode.text);
    if (code == null) {
      setState(
        () => _disableError = 'أدخل الرمز الحاليّ (6 أرقام) لتأكيد التعطيل',
      );
      return;
    }
    final ok = await showConfirmDialog(
      context,
      title: 'تعطيل المصادقة الثنائيّة؟',
      message:
          'سيصبح الدخول إلى حسابك بكلمة المرور وحدها. يمكنك تفعيلها من جديد '
          'في أيّ وقت.',
      confirmLabel: 'تعطيل',
      destructive: true,
    );
    if (!ok || !mounted) return;
    setState(() {
      _disableBusy = true;
      _disableError = null;
    });
    try {
      await _api.mfaDisable(code);
      if (mounted) {
        setState(() {
          _disabledOk = true;
          _showDisable = false;
          _disableCode.clear();
        });
      }
    } catch (e) {
      if (mounted) {
        setState(
          () => _disableError = _humanize(e, 'تعذّر تعطيل المصادقة الثنائيّة'),
        );
      }
    } finally {
      if (mounted) setState(() => _disableBusy = false);
    }
  }

  Future<void> _copySecret() async {
    final s = _secret;
    if (s == null) return;
    await Clipboard.setData(ClipboardData(text: s));
    if (mounted) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('نُسخ السرّ')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final styles = context.textStyles;
    return AppScaffold(
      title: 'المصادقة الثنائيّة',
      body: ListView(
        padding: const EdgeInsets.all(SahoolSpacing.lg),
        children: [
          Text(
            'طبقة حماية إضافيّة: عند الدخول يُطلَب رمز مؤقّت من تطبيق مصادقة '
            '(Google Authenticator أو Authy).',
            style: styles.bodyMedium?.copyWith(color: t.muted),
          ),
          const SizedBox(height: SahoolSpacing.lg),
          if (_activated)
            const _Note(
              key: ValueKey('mfa_activated'),
              message:
                  'فُعّلت المصادقة الثنائيّة. سيُطلب الرمز في الدخول القادم.',
            ),
          if (_disabledOk)
            const _Note(
              key: ValueKey('mfa_disabled'),
              message: 'عُطّلت المصادقة الثنائيّة.',
            ),

          // ── بدء الاقتران ──────────────────────────────────────
          if (_secret == null && !_activated)
            PrimaryButton(
              key: const ValueKey('mfa_start'),
              label: 'بدء تفعيل المصادقة الثنائيّة',
              icon: Icons.shield_outlined,
              loading: _busy,
              onPressed: _startSetup,
            ),

          // ── عرض السرّ + QR + رمز التفعيل ──────────────────────
          if (_secret != null) ...[
            _setupCard(context),
            const SizedBox(height: SahoolSpacing.lg),
            OtpCodeField(
              key: const ValueKey('mfa_activate_code'),
              controller: _activateCode,
              enabled: !_busy,
              label: 'الرمز من تطبيق المصادقة',
              onSubmitted: _activate,
            ),
            const SizedBox(height: SahoolSpacing.lg),
            PrimaryButton(
              key: const ValueKey('mfa_activate'),
              label: 'تفعيل',
              icon: Icons.check_circle_outline,
              loading: _busy,
              onPressed: _activate,
            ),
          ],

          if (_error != null) ...[
            const SizedBox(height: SahoolSpacing.md),
            _InlineError(message: _error!),
          ],

          // ── تعطيل MFA ────────────────────────────────────────
          const SizedBox(height: SahoolSpacing.xl),
          const Divider(),
          const SizedBox(height: SahoolSpacing.sm),
          if (!_showDisable)
            Align(
              alignment: AlignmentDirectional.centerStart,
              child: TextButton(
                key: const ValueKey('mfa_show_disable'),
                onPressed: () => setState(() {
                  _showDisable = true;
                  _disableError = null;
                  _disabledOk = false;
                }),
                child: const Text('تعطيل المصادقة الثنائيّة (إن كانت مفعّلة)'),
              ),
            )
          else ...[
            Text(
              'أدخل رمزاً صحيحاً حاليّاً لتأكيد التعطيل.',
              style: styles.bodyMedium?.copyWith(color: t.muted),
            ),
            const SizedBox(height: SahoolSpacing.sm),
            OtpCodeField(
              key: const ValueKey('mfa_disable_code'),
              controller: _disableCode,
              enabled: !_disableBusy,
              onSubmitted: _disable,
            ),
            const SizedBox(height: SahoolSpacing.md),
            PrimaryButton(
              key: const ValueKey('mfa_disable'),
              label: 'تعطيل',
              tone: ButtonTone.danger,
              loading: _disableBusy,
              onPressed: _disable,
            ),
            const SizedBox(height: SahoolSpacing.sm),
            SecondaryButton(
              label: 'إلغاء',
              onPressed: _disableBusy
                  ? null
                  : () => setState(() => _showDisable = false),
            ),
            if (_disableError != null) ...[
              const SizedBox(height: SahoolSpacing.md),
              _InlineError(message: _disableError!),
            ],
          ],
        ],
      ),
    );
  }

  // بطاقة الاقتران: QR (otpauth://) + السرّ نصّاً للإدخال اليدويّ.
  Widget _setupCard(BuildContext context) {
    final t = context.tokens;
    final styles = context.textStyles;
    return SectionCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'امسح رمز QR في تطبيق المصادقة، أو أدخل السرّ يدويّاً. '
            'يُعرَض مرّة واحدة فقط.',
            style: styles.bodySmall?.copyWith(color: t.muted),
          ),
          const SizedBox(height: SahoolSpacing.lg),
          Center(
            // رمز QR يحتاج خلفيّة بيضاء وحواف داكنة ليُقرأ في كلّ سمة.
            child: ColoredBox(
              color: Colors.white,
              child: Padding(
                padding: const EdgeInsets.all(SahoolSpacing.sm),
                child: QrImageView(
                  data: _provisioningUri!,
                  size: 200,
                  backgroundColor: Colors.white,
                ),
              ),
            ),
          ),
          const SizedBox(height: SahoolSpacing.lg),
          Text(
            'السرّ (للإدخال اليدويّ):',
            style: styles.bodySmall?.copyWith(color: t.muted),
          ),
          const SizedBox(height: SahoolSpacing.xs),
          Row(
            children: [
              Expanded(
                child: SelectableText(
                  _secret!,
                  textDirection: TextDirection.ltr,
                  style: styles.bodyLarge?.copyWith(
                    fontFamily: 'monospace',
                    letterSpacing: 1.2,
                  ),
                ),
              ),
              AppIconButton(
                icon: Icons.copy_rounded,
                tooltip: 'نسخ السرّ',
                onPressed: _copySecret,
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _Note extends StatelessWidget {
  const _Note({super.key, required this.message});
  final String message;

  @override
  Widget build(BuildContext context) {
    final color = context.tokens.success;
    return Semantics(
      liveRegion: true,
      child: Container(
        margin: const EdgeInsets.only(bottom: SahoolSpacing.lg),
        padding: const EdgeInsets.all(SahoolSpacing.md),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.12),
          borderRadius: SahoolRadius.mdAll,
          border: Border.all(color: color),
        ),
        child: Row(
          children: [
            Icon(Icons.check_circle_outline, color: color),
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

class _InlineError extends StatelessWidget {
  const _InlineError({required this.message});
  final String message;

  @override
  Widget build(BuildContext context) => Semantics(
    liveRegion: true,
    child: Text(
      message,
      style: context.textStyles.bodyMedium?.copyWith(
        color: context.tokens.danger,
      ),
    ),
  );
}
