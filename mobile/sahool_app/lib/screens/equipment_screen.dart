// SAHOOL — lib/screens/equipment_screen.dart
// المعدّات: الأسطول + سجلّ الصيانة، عبر /api/v1/equipment/*. مُقيَّد بالدور
// (equipment:view عرض، equipment:manage إضافة/صيانة). لا بيانات مُلفَّقة —
// حالة المعدّة وتكلفة الصيانة قرارات تشغيليّة، فالخطأ يُعلَن. تطابق EquipmentPage.
import 'package:flutter/material.dart';
import '../permissions.dart';
import '../services/api_service.dart';
import '../widgets/form_kit.dart';
import '../widgets/state_views.dart';

class EquipmentScreen extends StatefulWidget {
  const EquipmentScreen({super.key});
  @override
  State<EquipmentScreen> createState() => _EquipmentScreenState();
}

class _EquipmentScreenState extends State<EquipmentScreen> {
  bool _loading = true;
  String? _error;
  List<Map<String, dynamic>> _equipment = const [];

  static const _typeLabels = {
    'tractor': 'جرّار',
    'pump': 'مضخّة',
    'harvester': 'حصّادة',
    'sprayer': 'رشّاشة',
    'other': 'أخرى',
  };

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await ApiService.instance.getEquipment();
      if (!mounted) return;
      setState(() {
        _equipment = data;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = apiErrorMessage(e);
        _loading = false;
      });
    }
  }

  Color _statusColor(String status) {
    switch (status) {
      case 'active':
        return kPrimary;
      case 'maintenance':
        return kWarn;
      case 'broken':
        return Colors.redAccent;
      default:
        return Colors.grey;
    }
  }

  @override
  Widget build(BuildContext context) {
    final mutable = canMutate(currentRole());
    return Scaffold(
      backgroundColor: kBg,
      appBar: AppBar(
        backgroundColor: kSurface,
        title: const Text('المعدّات'),
        actions: [
          IconButton(onPressed: _load, icon: const Icon(Icons.refresh)),
        ],
      ),
      floatingActionButton: mutable
          ? FloatingActionButton.extended(
              backgroundColor: kPrimary,
              onPressed: _openAdd,
              icon: const Icon(Icons.add),
              label: const Text('معدّة جديدة'),
            )
          : null,
      body: _loading
          ? const LoadingView()
          : _error != null
              ? ErrorView(message: _error!, onRetry: _load)
              : _equipment.isEmpty
                  ? const EmptyView(message: 'لا توجد معدّات مسجّلة بعد')
                  : RefreshIndicator(
                      onRefresh: _load,
                      child: ListView.builder(
                        padding: const EdgeInsets.all(12),
                        itemCount: _equipment.length,
                        itemBuilder: (_, i) => _tile(_equipment[i], mutable),
                      ),
                    ),
    );
  }

  Widget _tile(Map<String, dynamic> eq, bool mutable) {
    final status = (eq['status'] ?? 'unknown').toString();
    final type = (eq['type'] ?? '').toString();
    final hours = eq['operating_hours'];
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: kSurface,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          Container(
            width: 10,
            height: 10,
            decoration: BoxDecoration(
                color: _statusColor(status), shape: BoxShape.circle),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('${eq['name'] ?? '—'}',
                    style: const TextStyle(
                        color: Colors.white, fontWeight: FontWeight.bold)),
                const SizedBox(height: 4),
                Text(
                  '${_typeLabels[type] ?? type} · ${hours ?? 0} ساعة تشغيل',
                  style: const TextStyle(color: Colors.grey, fontSize: 12),
                ),
              ],
            ),
          ),
          IconButton(
            icon: const Icon(Icons.build_outlined, color: kSecondary),
            tooltip: 'الصيانة',
            onPressed: () => _openMaintenance(eq, mutable),
          ),
        ],
      ),
    );
  }

  void _openAdd() {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: kSurface,
      isScrollControlled: true,
      builder: (_) => _AddEquipmentSheet(onDone: _load),
    );
  }

  void _openMaintenance(Map<String, dynamic> eq, bool mutable) {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => _MaintenanceScreen(equipment: eq, canLog: mutable),
      ),
    );
  }
}

class _AddEquipmentSheet extends StatefulWidget {
  final Future<void> Function() onDone;
  const _AddEquipmentSheet({required this.onDone});
  @override
  State<_AddEquipmentSheet> createState() => _AddEquipmentSheetState();
}

class _AddEquipmentSheetState extends State<_AddEquipmentSheet> {
  final _name = TextEditingController();
  final _hours = TextEditingController();
  String _type = 'tractor';
  bool _saving = false;

  static const _types = {
    'tractor': 'جرّار',
    'pump': 'مضخّة',
    'harvester': 'حصّادة',
    'sprayer': 'رشّاشة',
    'other': 'أخرى',
  };

  @override
  void dispose() {
    _name.dispose();
    _hours.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_name.text.trim().isEmpty) {
      showSnack(context, 'الاسم مطلوب', error: true);
      return;
    }
    setState(() => _saving = true);
    try {
      await ApiService.instance.createEquipment({
        'name': _name.text.trim(),
        'type': _type,
        if (_hours.text.trim().isNotEmpty)
          'operating_hours': double.tryParse(_hours.text.trim()) ?? 0,
      });
      if (!mounted) return;
      Navigator.pop(context);
      await widget.onDone();
    } catch (e) {
      if (mounted) {
        setState(() => _saving = false);
        showSnack(context, apiErrorMessage(e), error: true);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return SheetScaffold(
      title: 'معدّة جديدة',
      saving: _saving,
      onSubmit: _submit,
      children: [
        DropdownButtonFormField<String>(
          value: _type,
          dropdownColor: kSurface,
          decoration: kDec('النوع'),
          style: const TextStyle(color: Colors.white),
          items: _types.entries
              .map((e) => DropdownMenuItem(value: e.key, child: Text(e.value)))
              .toList(),
          onChanged: (v) => setState(() => _type = v ?? 'other'),
        ),
        kField(_name, 'الاسم'),
        kField(_hours, 'ساعات التشغيل', number: true),
      ],
    );
  }
}

class _MaintenanceScreen extends StatefulWidget {
  final Map<String, dynamic> equipment;
  final bool canLog;
  const _MaintenanceScreen({required this.equipment, required this.canLog});
  @override
  State<_MaintenanceScreen> createState() => _MaintenanceScreenState();
}

class _MaintenanceScreenState extends State<_MaintenanceScreen> {
  bool _loading = true;
  String? _error;
  List<Map<String, dynamic>> _records = const [];

  String get _equipmentId => widget.equipment['equipment_id'].toString();

  static const _kindLabels = {
    'scheduled': 'دوريّة',
    'repair': 'إصلاح',
    'breakdown': 'عطل',
    'inspection': 'فحص',
  };

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await ApiService.instance.getMaintenance(_equipmentId);
      if (!mounted) return;
      setState(() {
        _records = data;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = apiErrorMessage(e);
        _loading = false;
      });
    }
  }

  void _openLog() {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: kSurface,
      isScrollControlled: true,
      builder: (_) => _LogMaintenanceSheet(equipmentId: _equipmentId, onDone: _load),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: kBg,
      appBar: AppBar(
        backgroundColor: kSurface,
        title: Text('صيانة ${widget.equipment['name'] ?? ''}'),
      ),
      floatingActionButton: widget.canLog
          ? FloatingActionButton.extended(
              backgroundColor: kPrimary,
              onPressed: _openLog,
              icon: const Icon(Icons.add),
              label: const Text('تسجيل صيانة'),
            )
          : null,
      body: _loading
          ? const LoadingView()
          : _error != null
              ? ErrorView(message: _error!, onRetry: _load)
              : _records.isEmpty
                  ? const EmptyView(message: 'لا سجلّات صيانة')
                  : RefreshIndicator(
                      onRefresh: _load,
                      child: ListView.builder(
                        padding: const EdgeInsets.all(12),
                        itemCount: _records.length,
                        itemBuilder: (_, i) {
                          final r = _records[i];
                          final kind = (r['kind'] ?? '').toString();
                          final cost = r['cost_usd'];
                          return Container(
                            margin: const EdgeInsets.only(bottom: 10),
                            padding: const EdgeInsets.all(14),
                            decoration: BoxDecoration(
                              color: kSurface,
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  mainAxisAlignment:
                                      MainAxisAlignment.spaceBetween,
                                  children: [
                                    Text(_kindLabels[kind] ?? kind,
                                        style: const TextStyle(
                                            color: Colors.white,
                                            fontWeight: FontWeight.bold)),
                                    Text('${r['status'] ?? ''}',
                                        style: const TextStyle(
                                            color: Colors.grey, fontSize: 12)),
                                  ],
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  [
                                    if (r['performed_date'] != null)
                                      'نُفّذت: ${r['performed_date']}',
                                    if (r['scheduled_date'] != null)
                                      'مجدولة: ${r['scheduled_date']}',
                                    if (cost != null) 'التكلفة: \$$cost',
                                  ].join(' · '),
                                  style: const TextStyle(
                                      color: Colors.grey, fontSize: 12),
                                ),
                                if ((r['notes'] ?? '').toString().isNotEmpty) ...[
                                  const SizedBox(height: 4),
                                  Text('${r['notes']}',
                                      style: const TextStyle(
                                          color: Colors.white70, fontSize: 12)),
                                ],
                              ],
                            ),
                          );
                        },
                      ),
                    ),
    );
  }
}

class _LogMaintenanceSheet extends StatefulWidget {
  final String equipmentId;
  final Future<void> Function() onDone;
  const _LogMaintenanceSheet({required this.equipmentId, required this.onDone});
  @override
  State<_LogMaintenanceSheet> createState() => _LogMaintenanceSheetState();
}

class _LogMaintenanceSheetState extends State<_LogMaintenanceSheet> {
  final _cost = TextEditingController();
  final _notes = TextEditingController();
  final _performed = TextEditingController();
  String _kind = 'scheduled';
  String _status = 'done';
  bool _saving = false;

  static const _kinds = {
    'scheduled': 'دوريّة',
    'repair': 'إصلاح',
    'breakdown': 'عطل',
    'inspection': 'فحص',
  };
  static const _statuses = {
    'planned': 'مخطّطة',
    'done': 'مُنجَزة',
    'cancelled': 'ملغاة',
  };

  @override
  void dispose() {
    _cost.dispose();
    _notes.dispose();
    _performed.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() => _saving = true);
    try {
      await ApiService.instance.logMaintenance(widget.equipmentId, {
        'kind': _kind,
        'status': _status,
        if (_performed.text.trim().isNotEmpty)
          'performed_date': _performed.text.trim(),
        if (_cost.text.trim().isNotEmpty)
          'cost_usd': double.tryParse(_cost.text.trim()),
        if (_notes.text.trim().isNotEmpty) 'notes': _notes.text.trim(),
      });
      if (!mounted) return;
      Navigator.pop(context);
      await widget.onDone();
    } catch (e) {
      if (mounted) {
        setState(() => _saving = false);
        showSnack(context, apiErrorMessage(e), error: true);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return SheetScaffold(
      title: 'تسجيل صيانة',
      saving: _saving,
      onSubmit: _submit,
      children: [
        DropdownButtonFormField<String>(
          value: _kind,
          dropdownColor: kSurface,
          decoration: kDec('النوع'),
          style: const TextStyle(color: Colors.white),
          items: _kinds.entries
              .map((e) => DropdownMenuItem(value: e.key, child: Text(e.value)))
              .toList(),
          onChanged: (v) => setState(() => _kind = v ?? 'scheduled'),
        ),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(
          value: _status,
          dropdownColor: kSurface,
          decoration: kDec('الحالة'),
          style: const TextStyle(color: Colors.white),
          items: _statuses.entries
              .map((e) => DropdownMenuItem(value: e.key, child: Text(e.value)))
              .toList(),
          onChanged: (v) => setState(() => _status = v ?? 'done'),
        ),
        kField(_performed, 'تاريخ التنفيذ YYYY-MM-DD (اختياري)'),
        kField(_cost, 'التكلفة \$ (اختياري)', number: true),
        kField(_notes, 'ملاحظات (اختياري)'),
      ],
    );
  }
}
