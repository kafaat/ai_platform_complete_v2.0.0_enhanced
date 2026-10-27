// SAHOOL — lib/core/routing/route_pages.dart
// صفحات الموجِّه الصادقة: مسار غير معروف، دور غير مسموح، جلسة غائبة، معامل رابط
// ناقص. لا تُعرَض شاشة فارغة أو بيانات بديلة.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_navigator.dart';
import 'package:sahool_app/core/widgets/app_scaffold.dart';
import 'package:sahool_app/core/widgets/app_states.dart';

class RouteNotFoundPage extends StatelessWidget {
  const RouteNotFoundPage({super.key, required this.name});
  final String name;

  @override
  Widget build(BuildContext context) => AppScaffold(
        title: 'غير موجود',
        body: EmptyState(
          icon: Icons.link_off_rounded,
          title: 'الصفحة غير موجودة',
          message: 'الرابط «$name» لا يطابق أيّ شاشة في هذا الإصدار من التطبيق.',
        ),
      );
}

class AccessDeniedPage extends StatelessWidget {
  const AccessDeniedPage({super.key, required this.title});
  final String title;

  @override
  Widget build(BuildContext context) => AppScaffold(
        title: title,
        body: const EmptyState(
          icon: Icons.lock_outline_rounded,
          title: 'لا تملك صلاحيّة الوصول',
          message: 'هذا القسم متاح لأدوار الإدارة فقط. اطلب الصلاحيّة من مالك المزرعة.',
        ),
      );
}

/// مسار غير عامّ فُتح بلا جلسة (رابط عميق قبل الدخول): لا تُبنى الشاشة ولا
/// تُرسَل طلباتها. الجذر هو AuthGate فيعرض شاشة الدخول عند الرجوع إليه.
class SignInRequiredPage extends StatelessWidget {
  const SignInRequiredPage({super.key, required this.title});
  final String title;

  @override
  Widget build(BuildContext context) => AppScaffold(
        title: title,
        body: EmptyState(
          icon: Icons.login_rounded,
          title: 'سجّل الدخول أوّلاً',
          message: 'هذه الشاشة تتطلّب جلسة. سجّل الدخول ثمّ افتحها من جديد.',
          actionLabel: 'تسجيل الدخول',
          onAction: context.popToRoot,
        ),
      );
}

/// مسار خاصّ فُتح قبل حسم الجلسة (استعادتها من القرص أو تجديد رمزها): ينتظر
/// [pending] ثمّ يحكم مرّة واحدة عبر [resolve]. لا يُحكم على جلسة لم تُقرأ بعد
/// (كان رابط عميق عند الإقلاع يُعرض «سجّل الدخول» قبل قراءة الجلسة)، وفشل الشبكة
/// أثناء التجديد يُبقي رمز التحديث فيبقى الحكم «قابلة للاستئناف» لا «مرفوضة».
class SessionPendingPage extends StatefulWidget {
  const SessionPendingPage({
    super.key,
    required this.title,
    required this.pending,
    required this.resolve,
  });
  final String title;
  final Future<void> pending;
  final WidgetBuilder Function() resolve;

  @override
  State<SessionPendingPage> createState() => _SessionPendingPageState();
}

class _SessionPendingPageState extends State<SessionPendingPage> {
  WidgetBuilder? _page;

  @override
  void initState() {
    super.initState();
    widget.pending.then((_) {}, onError: (Object _) {}).whenComplete(() {
      if (mounted) setState(() => _page = widget.resolve());
    });
  }

  @override
  Widget build(BuildContext context) {
    final page = _page;
    if (page != null) return page(context);
    return AppScaffold(
      title: widget.title,
      body: const LoadingState(message: 'جارٍ التحقّق من الجلسة…'),
    );
  }
}

class MissingRouteParamPage extends StatelessWidget {
  const MissingRouteParamPage({super.key, required this.param});
  final String param;

  @override
  Widget build(BuildContext context) => AppScaffold(
        title: 'رابط ناقص',
        body: EmptyState(
          icon: Icons.link_off_rounded,
          title: 'الرابط ناقص',
          message: 'هذه الشاشة تحتاج المعامل «$param» في الرابط.',
        ),
      );
}
