// SAHOOL — lib/screens/fields_screen.dart
// إدارة الحقول (كان placeholder). يدمج OfflineFieldMap الجاهز (كان مبنيّاً وغير
// مستعمَل) + قائمة الحقول الحيّة من نظرة عامّة /indicators/v1/overview. تحليل
// دفاعيّ للشكل (قد تنقص الإحداثيّات ⇒ خريطة بلا مضلّعات، لا تعطّل). صدق: عند
// التعذّر يُعرَض خطأ بإعادة محاولة — لا بيانات مخترَعة.
import 'package:flutter/material.dart';
import 'package:latlong2/latlong.dart';
import '../services/api_service.dart';
import '../widgets/offline_field_map.dart';
import 'field_create_wizard.dart';

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

  // فتح معالج إنشاء الحقل (route: 'field_create'). يُعاد تحميل القائمة عند النجاح
  // (يردّ true). نستخدم MaterialPageRoute مباشرةً كي تعمل الشاشة حتّى لو لم يُسجّل
  // المسار في main.dart بعد (تسجيل المسارات مهمّة وكيل آخر — انظر ملاحظات الـPR).
  Future<void> _openCreateWizard() async {
    final created = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        settings: const RouteSettings(name: 'field_create'),
        builder: (_) => const FieldCreateWizard(),
      ),
    );
    if (created == true) await _load();
  }

  // الانتقال إلى مساحة عمل الحقل (route: 'field_workspace' — يبنيه وكيل آخر).
  // نمرّر معرّف الحقل كوسيط. pushNamed كي يربطه main.dart حين يُسجَّل المسار؛
  // نلتقط الفشل بهدوء (المسار غير مسجّل بعد) كي لا تتعطّل الشاشة.
  void _openWorkspace(String fieldId) {
    try {
      Navigator.of(context).pushNamed('field_workspace', arguments: fieldId);
    } catch (_) {
      // المسار غير مسجَّل بعد (وكيل آخر يبنيه) — أبلغ بهدوء بدل تعطّل.
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('مساحة عمل الحقل غير متاحة بعد')),
      );
    }
  }

  String _fieldId(Map<String, dynamic> f, int i) =>
      (f['field_id'] ?? f['id'] ?? f['fieldId'] ?? '$i').toString();

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
    return Scaffold(
      backgroundColor: Colors.transparent,
      // CTA واضح لإنشاء حقل (يفتح المعالج). يظهر دائماً ما لم نكن في حالة خطأ.
      floatingActionButton: (_loading || _error != null)
          ? null
          : FloatingActionButton.extended(
              backgroundColor: const Color(0xFF10B981),
              onPressed: _openCreateWizard,
              icon: const Icon(Icons.add),
              label: const Text('إضافة حقل'),
            ),
      body: SafeArea(child: _body()),
    );
  }

  Widget _body() {
    if (_loading) {
      return const Center(
          child: CircularProgressIndicator(color: Color(0xFF10B981)));
    }
    if (_error != null) {
      return Center(
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
      );
    }

    return Column(
      children: [
        // خريطة الحقول (offline-أوّلاً عبر الـwidget الجاهز).
        SizedBox(
          height: 240,
          child: OfflineFieldMap(center: _centerOf(_fields)),
        ),
        Expanded(
          child: _fields.isEmpty
              ? _emptyState()
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView.builder(
                    padding: const EdgeInsets.fromLTRB(12, 12, 12, 80),
                    itemCount: _fields.length,
                    itemBuilder: (ctx, i) => _fieldCard(_fields[i], i),
                  ),
                ),
        ),
      ],
    );
  }

  // حالة فارغة قابلة للفعل: أيقونة + نصّ + زرّ يفتح المعالج (بدل نصّ خامل).
  Widget _emptyState() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.terrain, color: Colors.grey, size: 56),
            const SizedBox(height: 14),
            const Text('لا توجد حقول مسجّلة بعد',
                style: TextStyle(color: Colors.white, fontSize: 16)),
            const SizedBox(height: 6),
            const Text('أنشئ حقلك الأوّل بالرسم على الخريطة أو استيراد حدوده.',
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.grey, fontSize: 13)),
            const SizedBox(height: 18),
            ElevatedButton.icon(
              onPressed: _openCreateWizard,
              icon: const Icon(Icons.add),
              label: const Text('إنشاء حقل'),
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF10B981),
                padding:
                    const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _fieldCard(Map<String, dynamic> f, int i) {
    final name = (f['field_name'] ?? f['name'] ?? 'حقل ${i + 1}').toString();
    final ndvi = _num(f['ndvi']);
    final area = _num(f['area_ha'] ?? f['area']);
    final crop = (f['crop'] ?? f['crop_ar'] ?? '').toString();
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1D29),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(12),
          // البطاقة قابلة للنقر → مساحة عمل الحقل (يبنيها وكيل آخر).
          onTap: () => _openWorkspace(_fieldId(f, i)),
          child: Padding(
            padding: const EdgeInsets.all(14),
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
                          if (area != null) '${area.toStringAsFixed(1)} هـ',
                        ].join(' · '),
                        style: const TextStyle(
                            color: Colors.grey, fontSize: 12),
                      ),
                    ],
                  ),
                ),
                const Icon(Icons.chevron_left, color: Colors.grey),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
