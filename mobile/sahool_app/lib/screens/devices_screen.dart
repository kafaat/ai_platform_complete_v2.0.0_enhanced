// SAHOOL — lib/screens/devices_screen.dart
// أجهزة IoT: سجلّ الأجهزة بمؤشّر اتصال online/offline (مُحتسَب خادميّاً من
// last_seen_at) + قياسات حيّة، عبر /api/v1/devices/*. مُقيَّد بالدور (device:view
// عرض، device:manage تسجيل، observation:record رفع قياس). لا قياسات مُلفَّقة —
// تُعرَض القياسات الحقيقيّة فقط. تطابق DevicesPage في الويب.
import 'package:flutter/material.dart';
import '../permissions.dart';
import '../services/api_service.dart';
import '../widgets/form_kit.dart';
import '../widgets/state_views.dart';

class DevicesScreen extends StatefulWidget {
  const DevicesScreen({super.key});
  @override
  State<DevicesScreen> createState() => _DevicesScreenState();
}

class _DevicesScreenState extends State<DevicesScreen> {
  bool _loading = true;
  String? _error;
  List<Map<String, dynamic>> _devices = const [];

  static const _typeLabels = {
    'soil_moisture': 'رطوبة التربة',
    'weather_station': 'محطّة طقس',
    'water_meter': 'عدّاد ماء',
    'camera': 'كاميرا',
    'actuator': 'مُشغِّل',
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
      final data = await ApiService.instance.listDevices();
      if (!mounted) return;
      setState(() {
        _devices = data;
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

  @override
  Widget build(BuildContext context) {
    final mutable = canMutate(currentRole());
    return Scaffold(
      backgroundColor: kBg,
      appBar: AppBar(
        backgroundColor: kSurface,
        title: const Text('أجهزة IoT'),
        actions: [
          IconButton(onPressed: _load, icon: const Icon(Icons.refresh)),
        ],
      ),
      floatingActionButton: mutable
          ? FloatingActionButton.extended(
              backgroundColor: kPrimary,
              onPressed: _openRegister,
              icon: const Icon(Icons.add),
              label: const Text('تسجيل جهاز'),
            )
          : null,
      body: _loading
          ? const LoadingView()
          : _error != null
              ? ErrorView(message: _error!, onRetry: _load)
              : _devices.isEmpty
                  ? const EmptyView(message: 'لا أجهزة مسجّلة بعد')
                  : RefreshIndicator(
                      onRefresh: _load,
                      child: ListView.builder(
                        padding: const EdgeInsets.all(12),
                        itemCount: _devices.length,
                        itemBuilder: (_, i) => _tile(_devices[i]),
                      ),
                    ),
    );
  }

  Widget _tile(Map<String, dynamic> d) {
    final online = d['online'] == true;
    final type = (d['type'] ?? '').toString();
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: kSurface,
        borderRadius: BorderRadius.circular(12),
      ),
      child: InkWell(
        onTap: () => Navigator.push(
          context,
          MaterialPageRoute(builder: (_) => _TelemetryScreen(device: d)),
        ),
        child: Row(
          children: [
            Container(
              width: 12,
              height: 12,
              decoration: BoxDecoration(
                color: online ? kPrimary : Colors.grey,
                shape: BoxShape.circle,
                boxShadow: online
                    ? [BoxShadow(color: kPrimary.withOpacity(0.6), blurRadius: 6)]
                    : null,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('${d['name'] ?? '—'}',
                      style: const TextStyle(
                          color: Colors.white, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 4),
                  Text(
                    '${_typeLabels[type] ?? type} · ${online ? 'متصل' : 'غير متصل'}',
                    style: TextStyle(
                        color: online ? kPrimary : Colors.grey, fontSize: 12),
                  ),
                ],
              ),
            ),
            const Icon(Icons.chevron_left, color: Colors.grey),
          ],
        ),
      ),
    );
  }

  void _openRegister() {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: kSurface,
      isScrollControlled: true,
      builder: (_) => _RegisterDeviceSheet(onDone: _load),
    );
  }
}

class _RegisterDeviceSheet extends StatefulWidget {
  final Future<void> Function() onDone;
  const _RegisterDeviceSheet({required this.onDone});
  @override
  State<_RegisterDeviceSheet> createState() => _RegisterDeviceSheetState();
}

class _RegisterDeviceSheetState extends State<_RegisterDeviceSheet> {
  final _name = TextEditingController();
  final _firmware = TextEditingController();
  String _type = 'soil_moisture';
  bool _saving = false;

  static const _types = {
    'soil_moisture': 'رطوبة التربة',
    'weather_station': 'محطّة طقس',
    'water_meter': 'عدّاد ماء',
    'camera': 'كاميرا',
    'actuator': 'مُشغِّل',
    'other': 'أخرى',
  };

  @override
  void dispose() {
    _name.dispose();
    _firmware.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_name.text.trim().isEmpty) {
      showSnack(context, 'الاسم مطلوب', error: true);
      return;
    }
    setState(() => _saving = true);
    try {
      await ApiService.instance.registerDevice({
        'name': _name.text.trim(),
        'type': _type,
        if (_firmware.text.trim().isNotEmpty)
          'firmware_version': _firmware.text.trim(),
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
      title: 'تسجيل جهاز',
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
        kField(_firmware, 'إصدار البرنامج الثابت (اختياري)'),
      ],
    );
  }
}

class _TelemetryScreen extends StatefulWidget {
  final Map<String, dynamic> device;
  const _TelemetryScreen({required this.device});
  @override
  State<_TelemetryScreen> createState() => _TelemetryScreenState();
}

class _TelemetryScreenState extends State<_TelemetryScreen> {
  bool _loading = true;
  String? _error;
  List<Map<String, dynamic>> _points = const [];

  String get _deviceId => widget.device['device_id'].toString();

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
      final data = await ApiService.instance.getDeviceTelemetry(_deviceId);
      if (!mounted) return;
      setState(() {
        _points = data;
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: kBg,
      appBar: AppBar(
        backgroundColor: kSurface,
        title: Text('قياسات ${widget.device['name'] ?? ''}'),
        actions: [
          IconButton(onPressed: _load, icon: const Icon(Icons.refresh)),
        ],
      ),
      body: _loading
          ? const LoadingView()
          : _error != null
              ? ErrorView(message: _error!, onRetry: _load)
              : _points.isEmpty
                  ? const EmptyView(
                      message: 'لا قياسات حديثة لهذا الجهاز',
                      icon: Icons.sensors_off)
                  : RefreshIndicator(
                      onRefresh: _load,
                      child: ListView.builder(
                        padding: const EdgeInsets.all(12),
                        itemCount: _points.length,
                        itemBuilder: (_, i) {
                          final p = _points[i];
                          return Container(
                            margin: const EdgeInsets.only(bottom: 8),
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: kSurface,
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                Text('${p['sensor_type'] ?? '—'}',
                                    style: const TextStyle(color: Colors.white)),
                                Text(
                                  '${p['value'] ?? ''} ${p['unit'] ?? ''}',
                                  style: const TextStyle(
                                      color: kSecondary,
                                      fontWeight: FontWeight.bold),
                                ),
                              ],
                            ),
                          );
                        },
                      ),
                    ),
    );
  }
}
