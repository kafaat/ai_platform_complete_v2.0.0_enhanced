// SAHOOL — lib/screens/satellite_screen.dart
// مؤشّرات الأقمار (كان placeholder). يختار المستخدم حقلاً (من النظرة العامّة)
// فتُجلَب مؤشّراته الحيّة عبر /indicators/v1/indicators/{fieldId} وتُعرَض كبطاقات.
// تحليل دفاعيّ (قائمة indicators أو مفاتيح رقميّة). صدق: التعذّر يُعلَن بإعادة محاولة.
import 'package:flutter/material.dart';
import '../services/api_service.dart';

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

  List<_Indicator> _parseIndicators(Map<String, dynamic> data) {
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
            const Text('مؤشّرات الأقمار الصناعيّة',
                style: TextStyle(
                    color: Colors.white,
                    fontSize: 18,
                    fontWeight: FontWeight.bold)),
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
