// SAHOOL — lib/screens/profile_screen.dart
// الحساب الشخصيّ (كان placeholder). يعرض ملفّ المستخدم من التخزين الآمن
// (الاسم/الدور/المستأجر) + الإصدار + تسجيل الخروج الفعليّ (POST /auth/logout
// ثمّ مسح الجلسة وإعادة AuthGate). الأدوار تُترجَم للعربيّة.
import 'package:flutter/material.dart';
import 'package:package_info_plus/package_info_plus.dart';
import '../main.dart';
import '../services/api_service.dart';
import '../services/auth_service.dart';

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  static const _roleAr = {
    'owner': 'مالك',
    'manager': 'مدير',
    'agronomist': 'مهندس زراعيّ',
    'expert': 'خبير',
    'worker': 'عامل',
    'farmer': 'مزارع',
    'viewer': 'مُشاهِد',
    'admin': 'مسؤول',
  };

  Future<void> _logout(BuildContext context) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF1A1D29),
        title: const Text('تسجيل الخروج',
            style: TextStyle(color: Colors.white)),
        content: const Text('هل تريد تسجيل الخروج من حسابك؟',
            style: TextStyle(color: Colors.grey)),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('إلغاء')),
          TextButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('خروج',
                  style: TextStyle(color: Color(0xFFF87171)))),
        ],
      ),
    );
    if (confirm != true) return;
    await ApiService.instance.logout(
        refreshToken: AuthService.instance.refreshToken);
    if (!context.mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const AuthGate()),
      (route) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    final profile = AuthService.instance.userProfile ?? const {};
    final name = (profile['full_name'] ?? 'مستخدم سهول').toString();
    final role = (profile['role'] ?? '').toString();
    final roleAr = _roleAr[role] ?? (role.isEmpty ? 'غير محدّد' : role);
    final tenant = (profile['tenant_id'] ?? '—').toString();

    return SafeArea(
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const SizedBox(height: 12),
          Center(
            child: CircleAvatar(
              radius: 44,
              backgroundColor: const Color(0xFF10B981),
              child: Text(
                name.isNotEmpty ? name.substring(0, 1) : '؟',
                style: const TextStyle(
                    color: Colors.white,
                    fontSize: 36,
                    fontWeight: FontWeight.bold),
              ),
            ),
          ),
          const SizedBox(height: 12),
          Center(
            child: Text(name,
                style: const TextStyle(
                    color: Colors.white,
                    fontSize: 20,
                    fontWeight: FontWeight.bold)),
          ),
          const SizedBox(height: 4),
          Center(
            child: Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
              decoration: BoxDecoration(
                color: const Color(0xFF10B981).withOpacity(0.15),
                borderRadius: BorderRadius.circular(20),
              ),
              child: Text(roleAr,
                  style: const TextStyle(
                      color: Color(0xFF10B981), fontSize: 13)),
            ),
          ),
          const SizedBox(height: 28),
          _tile(Icons.badge_outlined, 'الدور', roleAr),
          _tile(Icons.business_outlined, 'المستأجر', tenant),
          // الإصدار الفعليّ من الحزمة (لا قيمة ثابتة تتقادم).
          FutureBuilder<PackageInfo>(
            future: PackageInfo.fromPlatform(),
            builder: (ctx, snap) {
              final v = snap.hasData
                  ? 'سهول ${snap.data!.version} (${snap.data!.buildNumber})'
                  : 'سهول';
              return _tile(Icons.info_outline, 'إصدار التطبيق', v);
            },
          ),
          const SizedBox(height: 28),
          ElevatedButton.icon(
            onPressed: () => _logout(context),
            icon: const Icon(Icons.logout, color: Colors.white),
            label: const Text('تسجيل الخروج',
                style: TextStyle(color: Colors.white)),
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFFB91C1C),
              padding: const EdgeInsets.symmetric(vertical: 14),
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12)),
            ),
          ),
        ],
      ),
    );
  }

  Widget _tile(IconData icon, String label, String value) => Container(
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: const Color(0xFF1A1D29),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Row(
          children: [
            Icon(icon, color: const Color(0xFF10B981), size: 20),
            const SizedBox(width: 12),
            Text(label, style: const TextStyle(color: Colors.grey)),
            const Spacer(),
            Flexible(
              child: Text(value,
                  textAlign: TextAlign.left,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: Colors.white)),
            ),
          ],
        ),
      );
}
