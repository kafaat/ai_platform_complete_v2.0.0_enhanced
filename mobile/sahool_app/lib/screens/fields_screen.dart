// SAHOOL — lib/screens/fields_screen.dart
// إدارة الحقول (كان placeholder). يدمج OfflineFieldMap الجاهز (كان مبنيّاً وغير
// مستعمَل) + قائمة الحقول الحيّة من نظرة عامّة /indicators/v1/overview. تحليل
// دفاعيّ للشكل (قد تنقص الإحداثيّات ⇒ خريطة بلا مضلّعات، لا تعطّل). صدق: عند
// التعذّر يُعرَض خطأ بإعادة محاولة — لا بيانات مخترَعة.
import 'package:flutter/material.dart';
import 'package:latlong2/latlong.dart';
import '../services/api_service.dart';
import '../widgets/offline_field_map.dart';

class FieldsScreen extends StatefulWidget {
  const FieldsScreen({super.key});

  @override
  State<FieldsScreen> createState() => _FieldsScreenState();
}

class _FieldsScreenState extends State<FieldsScreen> {
  bool _loading = true;
  String? _error;
  List<Map<String, dynamic>> _fields = const [];

  // مركز افتراضيّ (اليمن) حين لا تتوفّر إحداثيّات من الخادم.
  static const _defaultCenter = LatLng(15.55, 47.5);

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
      final data = await ApiService.instance.getDashboard();
      setState(() {
        _fields = _extractFields(data);
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  // استخراج دفاعيّ: نقبل عدّة مفاتيح محتملة لقائمة الحقول.
  List<Map<String, dynamic>> _extractFields(Map<String, dynamic> data) {
    final raw = data['fields'] ?? data['fields_summary'] ?? data['field_list'];
    if (raw is List) {
      return raw.whereType<Map>().map((e) => e.cast<String, dynamic>()).toList();
    }
    return const [];
  }

  double? _num(dynamic v) => v is num ? v.toDouble() : double.tryParse('$v');

  LatLng _centerOf(List<Map<String, dynamic>> fields) {
    for (final f in fields) {
      final lat = _num(f['lat'] ?? f['latitude'] ?? f['centroid_lat']);
      final lon = _num(f['lon'] ?? f['lng'] ?? f['longitude'] ?? f['centroid_lon']);
      if (lat != null && lon != null) return LatLng(lat, lon);
    }
    return _defaultCenter;
  }

  Color _ndviColor(double? ndvi) {
    if (ndvi == null) return Colors.grey;
    if (ndvi >= 0.70) return const Color(0xFF16A34A);
    if (ndvi >= 0.50) return const Color(0xFF65A30D);
    if (ndvi >= 0.30) return const Color(0xFFCA8A04);
    return const Color(0xFFF97316);
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const SafeArea(
          child: Center(child: CircularProgressIndicator(color: Color(0xFF10B981))));
    }
    if (_error != null) {
      return SafeArea(
        child: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.error_outline, color: Colors.red, size: 44),
              const SizedBox(height: 12),
              const Text('تعذّر تحميل الحقول',
                  style: TextStyle(color: Colors.white)),
              const SizedBox(height: 12),
              ElevatedButton(
                  onPressed: _load, child: const Text('إعادة المحاولة')),
            ],
          ),
        ),
      );
    }

    return SafeArea(
      child: Column(
        children: [
          // خريطة الحقول (offline-أوّلاً عبر الـwidget الجاهز).
          SizedBox(
            height: 240,
            child: OfflineFieldMap(center: _centerOf(_fields)),
          ),
          Expanded(
            child: _fields.isEmpty
                ? const Center(
                    child: Text('لا توجد حقول مسجّلة بعد',
                        style: TextStyle(color: Colors.grey)))
                : RefreshIndicator(
                    onRefresh: _load,
                    child: ListView.builder(
                      padding: const EdgeInsets.all(12),
                      itemCount: _fields.length,
                      itemBuilder: (ctx, i) {
                        final f = _fields[i];
                        final name = (f['field_name'] ??
                                f['name'] ??
                                'حقل ${i + 1}')
                            .toString();
                        final ndvi = _num(f['ndvi']);
                        final area = _num(f['area_ha'] ?? f['area']);
                        final crop = (f['crop'] ?? f['crop_ar'] ?? '').toString();
                        return Container(
                          margin: const EdgeInsets.only(bottom: 10),
                          padding: const EdgeInsets.all(14),
                          decoration: BoxDecoration(
                            color: const Color(0xFF1A1D29),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Row(
                            children: [
                              Container(
                                width: 44,
                                height: 44,
                                decoration: BoxDecoration(
                                  color: _ndviColor(ndvi).withOpacity(0.15),
                                  borderRadius: BorderRadius.circular(10),
                                ),
                                child: Center(
                                  child: Text(
                                    ndvi != null ? ndvi.toStringAsFixed(2) : '—',
                                    style: TextStyle(
                                        color: _ndviColor(ndvi),
                                        fontWeight: FontWeight.bold),
                                  ),
                                ),
                              ),
                              const SizedBox(width: 12),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(name,
                                        style: const TextStyle(
                                            color: Colors.white,
                                            fontWeight: FontWeight.bold)),
                                    const SizedBox(height: 2),
                                    Text(
                                      [
                                        if (crop.isNotEmpty) crop,
                                        if (area != null)
                                          '${area.toStringAsFixed(1)} هـ',
                                      ].join(' · '),
                                      style: const TextStyle(
                                          color: Colors.grey, fontSize: 12),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        );
                      },
                    ),
                  ),
          ),
        ],
      ),
    );
  }
}
