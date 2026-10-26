// SAHOOL — features/profile/presentation/profile_screen.dart
// الحساب والإعدادات: الهويّة (من الجلسة ثمّ GET /api/v1/me)، الأمان (MFA)، المظهر
// (فاتح/داكن/حسب الجهاز عبر ThemeController)، اللغة، تفضيلات الإشعار (شاشة ميزة
// التنبيهات)، الإصدار، والخروج بتأكيد. كانت الشاشة بلا Scaffold فتُفتح من «المزيد»
// بلا شريط علويّ ولا زرّ رجوع ولا Material (نصّ مسطَّر).
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:sahool_app/core/routing/app_navigator.dart';
import 'package:sahool_app/core/routing/app_router.dart';
import 'package:sahool_app/core/session/auth_state.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/theme_controller.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/auth/auth_routes.dart';
import 'package:sahool_app/features/auth/data/auth_api.dart';
import 'package:sahool_app/features/profile/data/profile_api.dart';
import 'package:sahool_app/services/auth_service.dart';

import 'profile_cubit.dart';

/// مسار شاشة تفضيلات الإشعار في ميزة التنبيهات (تملكها ميزة alerts). يظهر
/// الرابط فعّالاً فقط حين يكون المسار مسجَّلاً في الموجِّه.
const String kNotificationPreferencesPath = '/alerts/preferences';

const Map<String, String> kRoleAr = {
  'owner': 'مالك',
  'manager': 'مدير',
  'agronomist': 'مهندس زراعيّ',
  'expert': 'خبير',
  'worker': 'عامل',
  'farmer': 'مزارع',
  'viewer': 'مُشاهِد',
  'admin': 'مسؤول',
};

String roleLabelAr(String? role) {
  if (role == null || role.isEmpty) return 'غير محدّد';
  return kRoleAr[role.toLowerCase()] ?? role;
}

/// يقرأ الإصدار الفعليّ من الحزمة (لا قيمة ثابتة تتقادم).
Future<String> packageVersionLabel() async {
  final info = await PackageInfo.fromPlatform();
  return '${info.version} (${info.buildNumber})';
}

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({
    super.key,
    this.api,
    this.session,
    this.themeController,
    this.versionLoader,
    this.logout,
    this.router,
  });

  // كلّها للاختبارات؛ الافتراضيّ الكائنات الحيّة.
  final ProfileApi? api;
  final Map<String, dynamic>? session;
  final ThemeController? themeController;
  final Future<String> Function()? versionLoader;
  final Future<void> Function()? logout;
  final AppRouter? router;

  @override
  Widget build(BuildContext context) => BlocProvider(
    create: (_) => ProfileCubit(
      api ?? ProfileApi.instance,
      session: session ?? AuthService.instance.userProfile,
    )..refresh(),
    child: _ProfileView(
      themeController: themeController ?? ThemeController.instance,
      versionLoader: versionLoader ?? packageVersionLabel,
      logout: logout ?? AuthApi.instance.logout,
      router: router ?? AppRouter.instance,
    ),
  );
}

class _ProfileView extends StatefulWidget {
  const _ProfileView({
    required this.themeController,
    required this.versionLoader,
    required this.logout,
    required this.router,
  });

  final ThemeController themeController;
  final Future<String> Function() versionLoader;
  final Future<void> Function() logout;
  final AppRouter router;

  @override
  State<_ProfileView> createState() => _ProfileViewState();
}

class _ProfileViewState extends State<_ProfileView> {
  late final Future<String> _version = widget.versionLoader();
  bool _loggingOut = false;

  Future<void> _confirmLogout() async {
    if (_loggingOut) return;
    final ok = await showConfirmDialog(
      context,
      title: 'تسجيل الخروج',
      message:
          'هل تريد تسجيل الخروج من حسابك؟ النماذج الميدانيّة التي لم تُرسل '
          'تبقى محفوظة على الجهاز وتُرسل عند دخولك من جديد.',
      confirmLabel: 'خروج',
      destructive: true,
    );
    if (!ok || !mounted) return;
    setState(() => _loggingOut = true);
    try {
      await widget.logout();
    } catch (_) {
      // ApiService.logout يمسح الجلسة محلّيّاً في finally مهما فشل الخادم.
    }
    // AuthGate يستمع إلى AuthState فيعرض شاشة الدخول؛ نُغلق المكدّس فوقه.
    AuthState.instance.signedOut();
    if (!mounted) return;
    setState(() => _loggingOut = false);
    context.popToRoot();
  }

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final styles = context.textStyles;
    final prefsAvailable =
        widget.router.match(kNotificationPreferencesPath) != null;
    return AppScaffold(
      title: 'الحساب والإعدادات',
      onRefresh: () => context.read<ProfileCubit>().refresh(),
      body: BlocBuilder<ProfileCubit, ProfileState>(
        builder: (context, state) {
          final id = state.identity;
          final name = id.name ?? 'مستخدم سهول';
          return ListView(
            padding: const EdgeInsetsDirectional.only(
              bottom: SahoolSpacing.xxl,
            ),
            children: [
              const SizedBox(height: SahoolSpacing.xl),
              Center(
                child: CircleAvatar(
                  radius: 40,
                  backgroundColor: context.colors.primary,
                  foregroundColor: context.colors.onPrimary,
                  child: Text(
                    name.characters.first,
                    style: styles.headlineMedium?.copyWith(
                      color: context.colors.onPrimary,
                      fontWeight: SahoolType.bold,
                    ),
                  ),
                ),
              ),
              const SizedBox(height: SahoolSpacing.md),
              Text(
                name,
                key: const ValueKey('profile_name'),
                textAlign: TextAlign.center,
                style: styles.titleLarge?.copyWith(fontWeight: SahoolType.bold),
              ),
              const SizedBox(height: SahoolSpacing.sm),
              Center(
                child: StatusChip(
                  label: roleLabelAr(id.role),
                  tone: StatusTone.info,
                  icon: Icons.badge_outlined,
                ),
              ),
              if (state.refreshing)
                const Padding(
                  padding: EdgeInsets.all(SahoolSpacing.sm),
                  child: LinearProgressIndicator(),
                ),
              if (state.error != null)
                Padding(
                  key: const ValueKey('profile_refresh_error'),
                  padding: const EdgeInsets.all(SahoolSpacing.lg),
                  child: Text(
                    'تعذّر تحديث بياناتك من الخادم: ${state.error!.messageAr} '
                    'المعروض من جلسة الدخول المحفوظة.',
                    textAlign: TextAlign.center,
                    style: styles.bodySmall?.copyWith(color: t.warning),
                  ),
                ),
              const ListSectionHeader('الحساب'),
              AppListTile(
                icon: Icons.badge_outlined,
                title: 'الدور',
                trailing: Text(roleLabelAr(id.role)),
              ),
              AppListTile(
                icon: Icons.business_outlined,
                title: 'المستأجر (المنشأة)',
                trailing: _Value(id.tenantId ?? 'غير متاح'),
              ),
              const AppListTile(
                key: ValueKey('profile_edit_unavailable'),
                icon: Icons.edit_outlined,
                title: 'تعديل الملفّ الشخصيّ',
                subtitle:
                    'غير متاح بعد: لا يوفّر الخادم نقطة لتعديل الاسم. اطلب '
                    'التعديل من مسؤول المنشأة.',
              ),
              const ListSectionHeader('الأمان'),
              AppListTile(
                key: const ValueKey('profile_mfa'),
                icon: Icons.shield_outlined,
                iconColor: context.colors.primary,
                title: 'المصادقة الثنائيّة',
                subtitle: 'رمز من تطبيق المصادقة عند كلّ دخول',
                onTap: () => context.openRoute<void>(AuthRoutes.mfa),
              ),
              const ListSectionHeader('المظهر'),
              Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: SahoolSpacing.lg,
                ),
                child: ValueListenableBuilder<ThemeMode>(
                  valueListenable: widget.themeController,
                  builder: (context, mode, _) => SegmentedButton<ThemeMode>(
                    key: const ValueKey('profile_theme'),
                    segments: const [
                      ButtonSegment(
                        value: ThemeMode.light,
                        icon: Icon(Icons.light_mode_outlined),
                        label: Text('فاتح'),
                      ),
                      ButtonSegment(
                        value: ThemeMode.dark,
                        icon: Icon(Icons.dark_mode_outlined),
                        label: Text('داكن'),
                      ),
                      ButtonSegment(
                        value: ThemeMode.system,
                        icon: Icon(Icons.settings_suggest_outlined),
                        label: Text('حسب الجهاز'),
                      ),
                    ],
                    selected: {mode},
                    showSelectedIcon: false,
                    onSelectionChanged: (s) =>
                        widget.themeController.setMode(s.first),
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsetsDirectional.fromSTEB(
                  SahoolSpacing.lg,
                  SahoolSpacing.sm,
                  SahoolSpacing.lg,
                  0,
                ),
                child: Text(
                  'الوضع الفاتح أوضح تحت الشمس.',
                  style: styles.bodySmall?.copyWith(color: t.muted),
                ),
              ),
              const ListSectionHeader('اللغة'),
              const AppListTile(
                icon: Icons.translate_outlined,
                title: 'العربيّة',
                subtitle: 'لغة التطبيق الوحيدة في هذا الإصدار.',
              ),
              const ListSectionHeader('الإشعارات'),
              AppListTile(
                key: const ValueKey('profile_notification_prefs'),
                icon: Icons.notifications_outlined,
                iconColor: prefsAvailable ? context.colors.primary : null,
                title: 'تفضيلات الإشعارات',
                subtitle: prefsAvailable
                    ? 'القنوات وأنواع التنبيهات'
                    : 'غير متاحة بعد في هذا الإصدار.',
                onTap: prefsAvailable
                    ? () =>
                          context.openRoute<void>(kNotificationPreferencesPath)
                    : null,
              ),
              const ListSectionHeader('حول التطبيق'),
              FutureBuilder<String>(
                future: _version,
                builder: (context, snap) => AppListTile(
                  key: const ValueKey('profile_version'),
                  icon: Icons.info_outline,
                  title: 'إصدار التطبيق',
                  trailing: _Value(
                    snap.hasData
                        ? snap.data!
                        : snap.hasError
                        ? 'غير متاح'
                        : '…',
                  ),
                ),
              ),
              const SizedBox(height: SahoolSpacing.xl),
              Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: SahoolSpacing.lg,
                ),
                child: PrimaryButton(
                  key: const ValueKey('profile_logout'),
                  label: 'تسجيل الخروج',
                  icon: Icons.logout_rounded,
                  tone: ButtonTone.danger,
                  loading: _loggingOut,
                  onPressed: _confirmLogout,
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

/// قيمة ذيليّة قصيرة تُقصّ بدل أن تدفع العنوان خارج الشاشة.
class _Value extends StatelessWidget {
  const _Value(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => ConstrainedBox(
    constraints: BoxConstraints(
      maxWidth: MediaQuery.sizeOf(context).width * 0.45,
    ),
    child: Text(
      text,
      overflow: TextOverflow.ellipsis,
      textAlign: TextAlign.end,
      style: context.textStyles.bodyMedium?.copyWith(
        color: context.tokens.muted,
      ),
    ),
  );
}
