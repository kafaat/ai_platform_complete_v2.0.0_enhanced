// SAHOOL — lib/screens/irrigation_ops_screen.dart
// الري التشغيلي: صمّامات + جداول الريّ، عبر /api/v1/irrigation/*. مُقيَّد بالدور
// (irrigation:view عرض، irrigation:manage إدارة). صدق: تغيير حالة الصمّام يسجّل
// النيّة فقط — التشغيل الفيزيائيّ يمرّ عبر موافقة بشريّة (HIL)، ولذا لافتة دائمة.
// لا fallback وهميّ. تطابق IrrigationOpsPage في الويب.
import 'package:flutter/material.dart';
import '../permissions.dart';
import '../services/api_service.dart';
import '../widgets/form_kit.dart';
import '../widgets/state_views.dart';

class IrrigationOpsScreen extends StatefulWidget {
  const IrrigationOpsScreen({super.key});
  @override
  State<IrrigationOpsScreen> createState() => _IrrigationOpsScreenState();
}

class _IrrigationOpsScreenState extends State<IrrigationOpsScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabs = TabController(length: 2, vsync: this);

  bool _loading = true;
  String? _error;
  List<Map<String, dynamic>> _valves = const [];
  List<Map<String, dynamic>> _schedules = const [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final valves = await ApiService.instance.listValves();
      final schedules = await ApiService.instance.listSchedules();
      if (!mounted) return;
      setState(() {
        _valves = valves;
        _schedules = schedules;
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

  Future<void> _setState(Map<String, dynamic> valve, String status) async {
    try {
      await ApiService.instance.setValveState(
          valve['valve_id'].toString(), status);
      if (mounted) {
        showSnack(context, 'سُجّلت النيّة — بانتظار موافقة بشريّة (HIL)');
      }
      await _load();
    } catch (e) {
      if (mounted) showSnack(context, apiErrorMessage(e), error: true);
    }
  }

  Future<void> _deleteSchedule(Map<String, dynamic> s) async {
    try {
      await ApiService.instance.deleteSchedule(s['schedule_id'].toString());
      await _load();
    } catch (e) {
      if (mounted) showSnack(context, apiErrorMessage(e), error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final mutable = canMutate(currentRole());
    return Scaffold(
      backgroundColor: kBg,
      appBar: AppBar(
        backgroundColor: kSurface,
        title: const Text('الري التشغيلي'),
        actions: [
          IconButton(onPressed: _load, icon: const Icon(Icons.refresh)),
        ],
        bottom: TabBar(
          controller: _tabs,
          indicatorColor: kPrimary,
          tabs: const [Tab(text: 'الصمّامات'), Tab(text: 'الجداول')],
        ),
      ),
      // FAB يتبع التبويب الحاليّ: AnimatedBuilder على TabController يعيد بناءه
      // عند السحب/التبديل، فلا يبقى نصّ التبويب الخاطئ معروضاً.
      floatingActionButton: mutable
          ? AnimatedBuilder(
              animation: _tabs,
              builder: (_, __) => FloatingActionButton.extended(
                backgroundColor: kPrimary,
                onPressed: () =>
                    _tabs.index == 0 ? _openAddValve() : _openAddSchedule(),
                icon: const Icon(Icons.add),
                label: Text(_tabs.index == 0 ? 'صمّام' : 'جدول'),
              ),
            )
          : null,
      body: _loading
          ? const LoadingView()
          : _error != null
              ? ErrorView(message: _error!, onRetry: _load)
              : Column(
                  children: [
                    const InfoBanner(
                      text:
                          'تغيير حالة الصمّام يسجّل النيّة فقط — التشغيل الفعليّ يتطلّب موافقة بشريّة (HIL).',
                    ),
                    Expanded(
                      child: TabBarView(
                        controller: _tabs,
                        children: [
                          _valvesTab(mutable),
                          _schedulesTab(mutable),
                        ],
                      ),
                    ),
                  ],
                ),
    );
  }

  Widget _valvesTab(bool mutable) {
    if (_valves.isEmpty) {
      return const EmptyView(message: 'لا صمّامات مسجّلة بعد');
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.builder(
        padding: const EdgeInsets.all(12),
        itemCount: _valves.length,
        itemBuilder: (_, i) {
          final v = _valves[i];
          final status = (v['status'] ?? 'unknown').toString();
          final open = status == 'open';
          return Container(
            margin: const EdgeInsets.only(bottom: 10),
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: kSurface,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(
              children: [
                Icon(Icons.water_drop,
                    color: open ? kSecondary : Colors.grey, size: 22),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('${v['name'] ?? '—'}',
                          style: const TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.bold)),
                      const SizedBox(height: 4),
                      Text(
                        open ? 'مفتوح' : (status == 'closed' ? 'مغلق' : 'غير معروف'),
                        style: TextStyle(
                            color: open ? kSecondary : Colors.grey,
                            fontSize: 12),
                      ),
                    ],
                  ),
                ),
                if (mutable)
                  Switch(
                    value: open,
                    activeColor: kSecondary,
                    onChanged: (val) =>
                        _setState(v, val ? 'open' : 'closed'),
                  ),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _schedulesTab(bool mutable) {
    if (_schedules.isEmpty) {
      return const EmptyView(message: 'لا جداول ريّ بعد');
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.builder(
        padding: const EdgeInsets.all(12),
        itemCount: _schedules.length,
        itemBuilder: (_, i) {
          final s = _schedules[i];
          final enabled = s['enabled'] == true;
          return Container(
            margin: const EdgeInsets.only(bottom: 10),
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: kSurface,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(
              children: [
                Icon(Icons.schedule,
                    color: enabled ? kPrimary : Colors.grey, size: 22),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('${s['name'] ?? '—'}',
                          style: const TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.bold)),
                      const SizedBox(height: 4),
                      Text(
                        '${s['start_time'] ?? ''} · ${s['duration_min'] ?? 0} دقيقة',
                        style:
                            const TextStyle(color: Colors.grey, fontSize: 12),
                      ),
                    ],
                  ),
                ),
                if (mutable)
                  IconButton(
                    icon: const Icon(Icons.delete_outline,
                        color: Colors.redAccent),
                    onPressed: () => _confirmDelete(s),
                  ),
              ],
            ),
          );
        },
      ),
    );
  }

  void _confirmDelete(Map<String, dynamic> s) {
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: kSurface,
        title: const Text('حذف الجدول', style: TextStyle(color: Colors.white)),
        content: Text('حذف "${s['name'] ?? ''}"؟',
            style: const TextStyle(color: Colors.white70)),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('إلغاء')),
          TextButton(
            onPressed: () {
              Navigator.pop(ctx);
              _deleteSchedule(s);
            },
            child: const Text('حذف', style: TextStyle(color: Colors.redAccent)),
          ),
        ],
      ),
    );
  }

  void _openAddValve() {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: kSurface,
      isScrollControlled: true,
      builder: (_) => _AddValveSheet(onDone: _load),
    );
  }

  void _openAddSchedule() {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: kSurface,
      isScrollControlled: true,
      builder: (_) => _AddScheduleSheet(onDone: _load),
    );
  }
}

class _AddValveSheet extends StatefulWidget {
  final Future<void> Function() onDone;
  const _AddValveSheet({required this.onDone});
  @override
  State<_AddValveSheet> createState() => _AddValveSheetState();
}

class _AddValveSheetState extends State<_AddValveSheet> {
  final _name = TextEditingController();
  final _flow = TextEditingController();
  String _type = 'solenoid';
  bool _saving = false;

  static const _types = {
    'solenoid': 'كهرومغناطيسيّ',
    'manual': 'يدويّ',
    'drip_header': 'رأس تنقيط',
    'gate': 'بوّابة',
  };

  @override
  void dispose() {
    _name.dispose();
    _flow.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_name.text.trim().isEmpty) {
      showSnack(context, 'الاسم مطلوب', error: true);
      return;
    }
    setState(() => _saving = true);
    try {
      await ApiService.instance.createValve({
        'name': _name.text.trim(),
        'valve_type': _type,
        if (_flow.text.trim().isNotEmpty)
          'flow_rate_lpm': double.tryParse(_flow.text.trim()),
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
      title: 'صمّام جديد',
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
          onChanged: (v) => setState(() => _type = v ?? 'solenoid'),
        ),
        kField(_name, 'الاسم'),
        kField(_flow, 'معدّل التدفّق (لتر/دقيقة) اختياري', number: true),
      ],
    );
  }
}

class _AddScheduleSheet extends StatefulWidget {
  final Future<void> Function() onDone;
  const _AddScheduleSheet({required this.onDone});
  @override
  State<_AddScheduleSheet> createState() => _AddScheduleSheetState();
}

class _AddScheduleSheetState extends State<_AddScheduleSheet> {
  final _name = TextEditingController();
  final _start = TextEditingController();
  final _duration = TextEditingController();
  bool _saving = false;

  @override
  void dispose() {
    _name.dispose();
    _start.dispose();
    _duration.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final duration = int.tryParse(_duration.text.trim());
    final start = _start.text.trim();
    if (_name.text.trim().isEmpty || start.isEmpty || duration == null) {
      showSnack(context, 'الاسم ووقت البدء والمدّة مطلوبة', error: true);
      return;
    }
    setState(() => _saving = true);
    try {
      await ApiService.instance.createSchedule({
        'name': _name.text.trim(),
        'start_time': start,
        'duration_min': duration,
        'enabled': true,
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
      title: 'جدول ريّ جديد',
      saving: _saving,
      onSubmit: _submit,
      children: [
        kField(_name, 'الاسم'),
        kField(_start, 'وقت البدء HH:MM'),
        kField(_duration, 'المدّة (دقيقة)', number: true),
      ],
    );
  }
}
