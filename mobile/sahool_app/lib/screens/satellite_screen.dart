// SAHOOL — lib/screens/satellite_screen.dart
// مؤشّرات الأقمار (كان placeholder). يختار المستخدم حقلاً (من النظرة العامّة)
// فتُجلَب مؤشّراته الحيّة عبر /api/vegetation/v1/analyze وتُعرَض كبطاقات. تحليل
// دفاعيّ (خريطة indices أو قائمة indicators أو مفاتيح رقميّة). زرّ تحديث صور
// Sentinel-2 (imagery/refresh) يُطلق المعالجة الحقيقيّة ويُبلِغ بالنتيجة بصدق.
import 'package:flutter/material.dart';
import '../services/api_service.dart';
import '../widgets/state_views.dart';

class SatelliteScreen extends StatefulWidget {
  const SatelliteScreen({super.key});

  @override
  State<SatelliteScreen> createState() => _SatelliteScreenState();
}

class _SatelliteScreenState extends State<SatelliteScreen> {
  List<Map<String, dynamic>> _fields = const [];
  String? _selectedId;
  bool _loadingFields = true;
  bool _loadingIndicators = false;
  bool _refreshingImagery = false;
  String? _error;
  List<_Indicator> _indicators = const [];

  @override
  void initState() {
    super.initState();
    _loadFields();
  }

  Future<void> _loadFields() async {
    setState(() {
      _loadingFields = true;
      _error = null;
    });
    try {
      final data = await ApiService.instance.getDashboard();
      final raw =
          data['fields'] ?? data['fields_summary'] ?? data['field_list'];
      final fields = raw is List
          ? raw.whereType<Map>().map((e) => e.cast<String, dynamic>()).toList()
          : <Map<String, dynamic>>[];
      setState(() {
        _fields = fields;
        _loadingFields = false;
      });
      if (fields.isNotEmpty) {
        final first = fields.first;
        _select((first['field_id'] ?? first['id'] ?? '').toString());
      }
    } catch (e) {
      setState(() {
        _error = e.toString();
        _loadingFields = false;
      });
    }
  }

  Future<void> _select(String fieldId) async {
    if (fieldId.isEmpty) return;
    setState(() {
      _selectedId = fieldId;
      _loadingIndicators = true;
      _error = null;
    });
    try {
      final data = await ApiService.instance.getFieldIndicators(fieldId);
      setState(() {
        _indicators = _parseIndicators(data);
        _loadingIndicators = false;
      });
    } catch (e) {
      setState(() {
        _error = e.toString();
        _loadingIndicators = false;
      });
    }
  }

  // يُطلق تحديث صور Sentinel-2 الحقيقيّة للحقل المُختار (imagery/refresh). صدق:
  // لا نزعم نجاحاً — نعرض رسالة من نتيجة الخادم (status/queued/note) أو الخطأ كما
  // هو. مُعطَّل حين لا حقل مُختار أو أثناء طلب جارٍ (يمنع طلبات متراكمة).
  Future<void> _refreshImagery() async {
    final id = _selectedId;
    if (id == null || id.isEmpty || _refreshingImagery) return;
    setState(() => _refreshingImagery = true);
    try {
      final result = await ApiService.instance.refreshFieldImagery(id);
      if (!mounted) return;
      final queued = result['queued'] == true;
      final status = (result['status'] ?? '').toString();
      final note = (result['note'] ?? result['message_ar'] ?? '').toString();
      final msg = queued
          ? 'تم إطلاق تحديث صور Sentinel-2 — قد يستغرق دقائق'
          : (note.isNotEmpty
              ? note
              : (status.isNotEmpty
                  ? 'حالة التحديث: $status'
                  : 'لا مشهد جديد متاح بعد لهذا الحقل'));
      showSnack(context, msg);
    } catch (e) {
      if (mounted) showSnack(context, apiErrorMessage(e), error: true);
    } finally {
      if (mounted) setState(() => _refreshingImagery = false);
    }
  }

  List<_Indicator> _parseIndicators(Map<String, dynamic> data) {
    // الشكل الثالث (المصدر الفعليّ — vegetation /v1/analyze): خريطة indices حيث
    // كلّ مفتاح (ndvi/evi/...) → {value, unit, source}. الحالة العامّة من
    // health['label_ar'] (تُعرَض على كلّ بطاقة بصدق — مصدر واحد للصحّة).
    final indices = data['indices'];
    if (indices is Map) {
      final health = data['health'];
      final statusAr = (health is Map)
          ? (health['label_ar'] ?? health['status'] ?? '').toString()
          : '';
      final out = <_Indicator>[];
      indices.forEach((k, v) {
        if (v is! Map) return;
        final inner = v.cast<String, dynamic>();
        out.add(_Indicator(
          name: k.toString().toUpperCase(),
          value: _fmt(inner['value']),
          unit: (inner['unit'] ?? '').toString(),
          status: statusAr,
        ));
      });
      if (out.isNotEmpty) return out;
    }
    // الشكل الأوّل: قائمة indicators صريحة.
    final list = data['indicators'];
    if (list is List) {
      return list.whereType<Map>().map((m) {
        final mm = m.cast<String, dynamic>();
        return _Indicator(
          name: (mm['name_ar'] ?? mm['name'] ?? mm['id'] ?? '').toString(),
          value: _fmt(mm['value']),
          unit: (mm['unit'] ?? '').toString(),
          status: (mm['status_ar'] ?? mm['status'] ?? '').toString(),
        );
      }).toList();
    }
    // الشكل الثاني: مفاتيح رقميّة عُليا (ndvi/evi/...).
    final out = <_Indicator>[];
    data.forEach((k, v) {
      if (v is num) out.add(_Indicator(name: k.toUpperCase(), value: _fmt(v)));
    });
    return out;
  }

  String _fmt(dynamic v) {
    if (v is num) return v.toStringAsFixed(v.abs() < 1 ? 3 : 2);
    return '$v';
  }

  @override
  Widget build(BuildContext context) {
    if (_loadingFields) {
      return const SafeArea(
          child: Center(
              child: CircularProgressIndicator(color: Color(0xFF10B981))));
    }
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                const Expanded(
                  child: Text('مؤشّرات الأقمار الصناعيّة',
                      style: TextStyle(
                          color: Colors.white,
                          fontSize: 18,
                          fontWeight: FontWeight.bold)),
                ),
                // تحديث صور Sentinel-2 الحقيقيّة للحقل المُختار — مُعطَّل بلا حقل
                // أو أثناء طلب جارٍ. مؤشّر دوّار أثناء الطلب بدل الأيقونة.
                IconButton(
                  tooltip: 'تحديث صور الأقمار',
                  onPressed: (_selectedId == null || _refreshingImagery)
                      ? null
                      : _refreshImagery,
                  icon: _refreshingImagery
                      ? const SizedBox(
                          height: 18,
                          width: 18,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: Color(0xFF10B981)),
                        )
                      : const Icon(Icons.satellite_alt, color: Colors.white),
                ),
              ],
            ),
            const SizedBox(height: 12),
            if (_error != null && _fields.isEmpty)
              // لا نُخفي خطأ الشبكة خلف «لا توجد حقول» — نُعلنه مع إعادة محاولة.
              Expanded(
                child: Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(Icons.error_outline, color: Colors.red, size: 40),
                      const SizedBox(height: 10),
                      const Text('تعذّر تحميل الحقول',
                          style: TextStyle(color: Colors.white)),
                      const SizedBox(height: 10),
                      ElevatedButton(
                          onPressed: _loadFields,
                          child: const Text('إعادة المحاولة')),
                    ],
                  ),
                ),
              )
            else if (_fields.isEmpty)
              const Expanded(
                child: Center(
                    child: Text('لا توجد حقول لعرض مؤشّراتها',
                        style: TextStyle(color: Colors.grey))),
              )
            else ...[
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12),
                decoration: BoxDecoration(
                  color: const Color(0xFF1A1D29),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: DropdownButtonHideUnderline(
                  child: DropdownButton<String>(
                    isExpanded: true,
                    dropdownColor: const Color(0xFF1A1D29),
                    value: _selectedId,
                    style: const TextStyle(color: Colors.white),
                    hint: const Text('اختر حقلاً',
                        style: TextStyle(color: Colors.grey)),
                    items: _fields.map((f) {
                      final id = (f['field_id'] ?? f['id'] ?? '').toString();
                      final name =
                          (f['field_name'] ?? f['name'] ?? id).toString();
                      return DropdownMenuItem(value: id, child: Text(name));
                    }).toList(),
                    onChanged: (v) {
                      if (v != null) _select(v);
                    },
                  ),
                ),
              ),
              const SizedBox(height: 16),
              Expanded(child: _body()),
            ],
          ],
        ),
      ),
    );
  }

  Widget _body() {
    if (_loadingIndicators) {
      return const Center(
          child: CircularProgressIndicator(color: Color(0xFF10B981)));
    }
    if (_error != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.error_outline, color: Colors.red, size: 40),
            const SizedBox(height: 10),
            const Text('تعذّر تحميل المؤشّرات',
                style: TextStyle(color: Colors.white)),
            const SizedBox(height: 10),
            ElevatedButton(
              onPressed: _selectedId != null ? () => _select(_selectedId!) : null,
              child: const Text('إعادة المحاولة'),
            ),
          ],
        ),
      );
    }
    if (_indicators.isEmpty) {
      return const Center(
          child: Text('لا مؤشّرات متاحة لهذا الحقل',
              style: TextStyle(color: Colors.grey)));
    }
    return GridView.count(
      crossAxisCount: 2,
      mainAxisSpacing: 12,
      crossAxisSpacing: 12,
      childAspectRatio: 1.4,
      children: _indicators.map((ind) {
        return Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: const Color(0xFF1A1D29),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(ind.name,
                  style: const TextStyle(color: Colors.grey, fontSize: 12)),
              const SizedBox(height: 6),
              Row(
                crossAxisAlignment: CrossAxisAlignment.baseline,
                textBaseline: TextBaseline.alphabetic,
                children: [
                  Text(ind.value,
                      style: const TextStyle(
                          color: Colors.white,
                          fontSize: 22,
                          fontWeight: FontWeight.bold)),
                  if (ind.unit.isNotEmpty) ...[
                    const SizedBox(width: 4),
                    Text(ind.unit,
                        style:
                            const TextStyle(color: Colors.grey, fontSize: 12)),
                  ],
                ],
              ),
              if (ind.status.isNotEmpty) ...[
                const SizedBox(height: 4),
                Text(ind.status,
                    style: const TextStyle(
                        color: Color(0xFF10B981), fontSize: 11)),
              ],
            ],
          ),
        );
      }).toList(),
    );
  }
}

class _Indicator {
  final String name;
  final String value;
  final String unit;
  final String status;
  const _Indicator({
    required this.name,
    required this.value,
    this.unit = '',
    this.status = '',
  });
}
