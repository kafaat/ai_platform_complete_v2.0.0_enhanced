// SAHOOL — lib/widgets/state_views.dart
// حالات موحّدة (تحميل/خطأ/فارغ) + ترجمة رمز خطأ الخادم لرسالة عربيّة صادقة،
// موازية لـfrontend StateViews. لا بيانات مُلفَّقة: 503 ⇒ قاعدة البيانات معطّلة،
// 403 ⇒ لا صلاحيّة، 401 ⇒ انتهت الجلسة. تُعرَض الحالة كما هي بلا اختلاق.
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';

const kBg = Color(0xFF0F1117);
const kSurface = Color(0xFF1A1D29);
const kPrimary = Color(0xFF10B981);
const kSecondary = Color(0xFF3B82F6);
const kWarn = Color(0xFFF59E0B);

/// رسالة خطأ صادقة حسب رمز الحالة من الخادم (يطابق منطق الواجهة).
String apiErrorMessage(Object e) {
  if (e is DioException) {
    final code = e.response?.statusCode;
    if (code == 503) {
      return 'الخدمة غير متاحة حاليّاً (قاعدة البيانات معطّلة على الخادم).';
    }
    if (code == 403) return 'لا تملك صلاحيّة الوصول إلى هذا القسم.';
    if (code == 401) return 'انتهت الجلسة — يُرجى تسجيل الدخول من جديد.';
    if (code == 404) return 'العنصر غير موجود.';
    if (code == 409) return 'تعارض: السجلّ موجود مسبقاً.';
    if (e.type == DioExceptionType.connectionError ||
        e.type == DioExceptionType.unknown) {
      return 'تعذّر الاتصال بالخادم — تحقّق من الشبكة.';
    }
    final detail = e.response?.data;
    if (detail is Map && detail['detail'] != null) {
      return detail['detail'].toString();
    }
  }
  return 'حدث خطأ غير متوقّع.';
}

class LoadingView extends StatelessWidget {
  const LoadingView({super.key});
  @override
  Widget build(BuildContext context) =>
      const Center(child: CircularProgressIndicator(color: kPrimary));
}

class ErrorView extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;
  const ErrorView({super.key, required this.message, required this.onRetry});
  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.error_outline, color: Colors.redAccent, size: 44),
              const SizedBox(height: 12),
              Text(message,
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Colors.white70)),
              const SizedBox(height: 16),
              ElevatedButton(
                onPressed: onRetry,
                style: ElevatedButton.styleFrom(backgroundColor: kPrimary),
                child: const Text('إعادة المحاولة'),
              ),
            ],
          ),
        ),
      );
}

class EmptyView extends StatelessWidget {
  final String message;
  final IconData icon;
  const EmptyView({
    super.key,
    required this.message,
    this.icon = Icons.inbox_outlined,
  });
  @override
  Widget build(BuildContext context) => Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, color: Colors.grey, size: 40),
            const SizedBox(height: 10),
            Text(message, style: const TextStyle(color: Colors.grey)),
          ],
        ),
      );
}

/// لافتة معلومة صادقة (HIL للريّ، الوثائق metadata فقط…).
class InfoBanner extends StatelessWidget {
  final String text;
  final Color color;
  const InfoBanner({super.key, required this.text, this.color = kWarn});
  @override
  Widget build(BuildContext context) => Container(
        width: double.infinity,
        margin: const EdgeInsets.fromLTRB(12, 12, 12, 0),
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: color.withOpacity(0.12),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: color.withOpacity(0.4)),
        ),
        child: Row(
          children: [
            Icon(Icons.info_outline, color: color, size: 18),
            const SizedBox(width: 8),
            Expanded(
              child: Text(text, style: TextStyle(color: color, fontSize: 12)),
            ),
          ],
        ),
      );
}

/// SnackBar موحّد للنجاح/الخطأ بعد الطفرات.
void showSnack(BuildContext context, String message, {bool error = false}) {
  if (!context.mounted) return;
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(
      content: Text(message),
      backgroundColor: error ? Colors.red.shade700 : kPrimary,
      behavior: SnackBarBehavior.floating,
    ),
  );
}
