// SAHOOL — lib/screens/more_screen.dart
// «المزيد»: شبكة وصول للوحدات الثانويّة التي خرجت من شريط التنقّل السفليّ بعد
// إعادة الترتيب لصالح المزارع (لوحة/حقول/عمليّات/مستشار). تُعيد استعمال الشاشات
// القائمة كما هي (لا منطق جديد) وتفتحها بـMaterialPageRoute. البيانات المرجعيّة
// والوثائق تُرشَّح بصلاحيّة الدور (RBAC فعليّ — تطابق canManage) كما في مركز العمليّات.
import 'package:flutter/material.dart';
import '../permissions.dart';
import '../widgets/state_views.dart';
import 'devices_screen.dart';
import 'documents_screen.dart';
import 'equipment_screen.dart';
import 'inventory_screen.dart';
import 'master_data_screen.dart';
import 'operations_hub_screen.dart';
import 'profile_screen.dart';
import 'satellite_screen.dart';

class _MoreItem {
  final String label;
  final IconData icon;
  final Widget Function() build;
  final bool managementOnly;
  const _MoreItem(this.label, this.icon, this.build,
      {this.managementOnly = false});
}

class MoreScreen extends StatelessWidget {
  const MoreScreen({super.key});

  static final List<_MoreItem> _items = [
    // مركز العمليّات (تجميعة الوحدات التشغيليّة) — خرج من شريط FieldView لكنّه
    // يبقى مُتاحاً هنا بالكامل (لم يُحذَف).
    _MoreItem('مركز العمليّات', Icons.grid_view,
        () => const OperationsHubScreen()),
    _MoreItem('الأقمار', Icons.satellite_alt, () => const SatelliteScreen()),
    _MoreItem('المخزون', Icons.inventory_2_outlined,
        () => const InventoryScreen()),
    _MoreItem('المعدّات', Icons.agriculture_outlined,
        () => const EquipmentScreen()),
    _MoreItem('أجهزة IoT', Icons.sensors, () => const DevicesScreen()),
    _MoreItem('البيانات المرجعيّة', Icons.storage_outlined,
        () => const MasterDataScreen(),
        managementOnly: true),
    _MoreItem('الوثائق', Icons.folder_outlined, () => const DocumentsScreen(),
        managementOnly: true),
    _MoreItem('الحساب والإعدادات', Icons.settings_outlined,
        () => const ProfileScreen()),
  ];

  @override
  Widget build(BuildContext context) {
    final manageable = canManage(currentRole());
    final visible =
        _items.where((m) => !m.managementOnly || manageable).toList();

    return Scaffold(
      backgroundColor: kBg,
      appBar: AppBar(
        backgroundColor: kSurface,
        title: const Text('المزيد'),
        automaticallyImplyLeading: false,
      ),
      body: SafeArea(
        child: GridView.builder(
          padding: const EdgeInsets.all(16),
          gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: 2,
            mainAxisSpacing: 12,
            crossAxisSpacing: 12,
            childAspectRatio: 1.1,
          ),
          itemCount: visible.length,
          itemBuilder: (_, i) {
            final m = visible[i];
            return InkWell(
              borderRadius: BorderRadius.circular(14),
              onTap: () => Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => m.build()),
              ),
              child: Container(
                decoration: BoxDecoration(
                  color: kSurface,
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: Colors.white10),
                ),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(m.icon, color: kPrimary, size: 36),
                    const SizedBox(height: 12),
                    Text(m.label,
                        textAlign: TextAlign.center,
                        style: const TextStyle(
                            color: Colors.white, fontWeight: FontWeight.bold)),
                  ],
                ),
              ),
            );
          },
        ),
      ),
    );
  }
}
