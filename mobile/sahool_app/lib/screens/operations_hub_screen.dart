// SAHOOL — lib/screens/operations_hub_screen.dart
// مركز العمليّات: شبكة وحدات تشغيليّة (مخزون/معدّات/أجهزة/ريّ تشغيلي/بيانات
// مرجعيّة/وثائق) مُرشَّحة بصلاحيّة الدور (RBAC فعليّ — تطابق canAccess في الواجهة):
//   • المخزون/المعدّات/الأجهزة/الري التشغيلي: متاحة لكلّ الأدوار (عرض).
//   • البيانات المرجعيّة/الوثائق: إدارة فقط (owner/manager) — لا تظهر لغيرهم.
import 'package:flutter/material.dart';
import '../permissions.dart';
import '../widgets/state_views.dart';
import 'devices_screen.dart';
import 'documents_screen.dart';
import 'equipment_screen.dart';
import 'inventory_screen.dart';
import 'irrigation_ops_screen.dart';
import 'master_data_screen.dart';
import 'tasks_screen.dart';

class _Module {
  final String label;
  final IconData icon;
  final Widget Function() build;
  final bool managementOnly;
  const _Module(this.label, this.icon, this.build, {this.managementOnly = false});
}

class OperationsHubScreen extends StatelessWidget {
  const OperationsHubScreen({super.key});

  static final List<_Module> _modules = [
    _Module('المخزون', Icons.inventory_2_outlined, () => const InventoryScreen()),
    _Module('المهام اليومية', Icons.task_alt_outlined, () => const TasksScreen()),
    _Module('المعدّات', Icons.agriculture_outlined, () => const EquipmentScreen()),
    _Module('أجهزة IoT', Icons.sensors, () => const DevicesScreen()),
    _Module('الري التشغيلي', Icons.water_drop_outlined,
        () => const IrrigationOpsScreen()),
    _Module('البيانات المرجعيّة', Icons.storage_outlined,
        () => const MasterDataScreen(),
        managementOnly: true),
    _Module('الوثائق', Icons.folder_outlined, () => const DocumentsScreen(),
        managementOnly: true),
  ];

  @override
  Widget build(BuildContext context) {
    final manageable = canManage(currentRole());
    final visible =
        _modules.where((m) => !m.managementOnly || manageable).toList();

    return Scaffold(
      backgroundColor: kBg,
      appBar: AppBar(
        backgroundColor: kSurface,
        title: const Text('العمليّات'),
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
                            color: Colors.white,
                            fontWeight: FontWeight.bold)),
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
