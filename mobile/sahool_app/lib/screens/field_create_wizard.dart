// SAHOOL — lib/screens/field_create_wizard.dart
// معالج إنشاء حقل متعدّد الخطوات (route: 'field_create'). يسدّ أهمّ فجوة:
// إنشاء الحقول الفعليّ. خطوات: (1) الاسم، (2) رسم/استيراد الحدّ على الخريطة،
// (3) المحصول، (4) مصدر المياه + نوع الريّ، (5) متقدّم اختياريّ (نوع التربة/المدير).
// «الملء التدريجيّ»: الخطوات 3-5 اختياريّة عمليّاً؛ الإلزاميّ اسم + مضلّع مغلق.
//
// الرسم يعيد استخدام OfflineFieldMap في وضع drawingEnabled (إضافة نقطة/تراجع/مسح).
// الاستيراد: لصق GeoJSON يعمل فعليّاً؛ KML نصّ يعمل عبر الخادم؛ GPS-walk «قريباً».
// عند الحفظ: createField (أو importFieldGeoJson) ثمّ — إن أُدخل نوع ريّ — updateField
// بـirrigation_type (PATCH)، ثمّ Navigator.pop(true). صدق: الخطأ يُعرَض كما هو.
import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:latlong2/latlong.dart';

import '../services/api_service.dart';
import '../widgets/form_kit.dart';
import '../widgets/offline_field_map.dart';
import '../widgets/state_views.dart';

class FieldCreateWizard extends StatefulWidget {
  const FieldCreateWizard({super.key});

  @override
  State<FieldCreateWizard> createState() => _FieldCreateWizardState();
}

class _FieldCreateWizardState extends State<FieldCreateWizard> {
  // مركز افتراضيّ (اليمن) حين لا تتوفّر إحداثيّات.
  static const _defaultCenter = LatLng(15.55, 47.5);

  int _step = 0;
  bool _saving = false;

  // الخطوة 1: الاسم.
  final _name = TextEditingController();

  // الخطوة 2: طريقة تحديد الحدّ + المضلّع.
  // 'draw' رسم يدويّ، 'geojson' لصق نصّ، 'kml' لصق نصّ، 'gps' قريباً.
  String _method = 'draw';
  final List<LatLng> _points = [];
  final _geojsonText = TextEditingController();
  // عند الاستيراد: نحتفظ بالنصّ الخام لإرساله للخادم (يحلّله هو).
  Map<String, dynamic>? _importedGeometry; // معاينة محليّة للمساحة فقط

  // الخطوة 3: المحصول.
  String? _crop;

  // الخطوة 4: مصدر المياه + نوع الريّ.
  String? _waterSource;
  String? _irrigationType;

  // الخطوة 5: متقدّم (اختياريّ).
  String? _soilType;
  final _manager = TextEditingController();

  // قوائم مرجعيّة (عربيّ ← قيمة الخادم). تطابق المتوقَّع خادميّاً (نصوص حرّة قصيرة).
  static const _crops = {
    'wheat': 'قمح',
    'barley': 'شعير',
    'sorghum': 'ذرة رفيعة',
    'maize': 'ذرة شاميّة',
    'coffee': 'بنّ',
    'qat': 'قات',
    'vegetables': 'خضروات',
    'fruits': 'فواكه',
    'alfalfa': 'برسيم',
    'other': 'أخرى',
  };
  static const _waterSources = {
    'well': 'بئر',
    'spring': 'نبع',
    'rain': 'أمطار',
    'canal': 'قناة',
    'tanker': 'صهريج',
    'network': 'شبكة',
  };
  static const _irrigationTypes = {
    'drip': 'تنقيط',
    'pivot': 'محوريّ',
    'flood': 'غمر',
    'sprinkler': 'رشّ',
    'rainfed': 'بعليّ (مطريّ)',
    'subsurface': 'تحت سطحيّ',
  };
  static const _soilTypes = {
    'sandy': 'رمليّة',
    'clay': 'طينيّة',
    'loam': 'طميّيّة',
    'silt': 'غرينيّة',
    'rocky': 'صخريّة',
  };

  @override
  void dispose() {
    _name.dispose();
    _geojsonText.dispose();
    _manager.dispose();
    super.dispose();
  }

  // ── منطق الرسم (مصدر الحقيقة: _points) ──
  void _onPolygonChanged(List<LatLng> updated) {
    setState(() {
      _points
        ..clear()
        ..addAll(updated);
    });
  }

  void _undoPoint() {
    if (_points.isEmpty) return;
    setState(() => _points.removeLast());
  }

  void _clearPoints() => setState(() => _points.clear());

  // مضلّع صالح للرسم = ≥3 رؤوس (نُغلقه آليّاً عند الإرسال).
  bool get _hasDrawnPolygon => _points.length >= 3;

  // هل لدينا حدّ صالح حسب الطريقة (يُفعّل زرّ الحفظ)؟
  bool get _boundaryReady {
    switch (_method) {
      case 'draw':
        return _hasDrawnPolygon;
      case 'geojson':
      case 'kml':
        return _geojsonText.text.trim().isNotEmpty;
      default:
        return false; // gps: قريباً
    }
  }

  // مركز الخريطة: أوّل نقطة مرسومة إن وُجدت، وإلّا الافتراضيّ.
  LatLng get _mapCenter => _points.isNotEmpty ? _points.first : _defaultCenter;

  // ── حساب المساحة (تقدير محليّ للعرض فقط — الخادم هو المرجع النهائيّ) ──
  // إسقاط متساوي المستطيلات حول مركز المضلّع ثمّ صيغة الحذّاء (shoelace).
  double _areaHa(List<LatLng> pts) {
    if (pts.length < 3) return 0;
    const earthR = 6378137.0; // نصف قطر الأرض (م)
    final lat0 = pts.map((p) => p.latitude).reduce((a, b) => a + b) / pts.length;
    final cosLat0 = math.cos(lat0 * math.pi / 180.0);
    final xy = pts
        .map((p) => [
              earthR * (p.longitude * math.pi / 180.0) * cosLat0,
              earthR * (p.latitude * math.pi / 180.0),
            ])
        .toList();
    var sum = 0.0;
    for (var i = 0; i < xy.length; i++) {
      final j = (i + 1) % xy.length;
      sum += xy[i][0] * xy[j][1] - xy[j][0] * xy[i][1];
    }
    final areaM2 = sum.abs() / 2.0;
    return areaM2 / 10000.0; // م² → هكتار
  }

  // مضلّع GeoJSON من الرؤوس المرسومة (حلقة مغلقة، ترتيب [lon,lat]).
  Map<String, dynamic> _geometryFromPoints() {
    final ring = _points
        .map((p) => [p.longitude, p.latitude])
        .toList(growable: true);
    // إغلاق الحلقة (أوّل = آخر) كما يتطلّب GeoJSON Polygon.
    if (ring.isNotEmpty &&
        (ring.first[0] != ring.last[0] || ring.first[1] != ring.last[1])) {
      ring.add([ring.first[0], ring.first[1]]);
    }
    return {
      'type': 'Polygon',
      'coordinates': [ring],
    };
  }

  // معاينة مساحة الاستيراد محليّاً (إن أمكن تحليل النصّ كـGeoJSON Polygon بسيط).
  // فشل التحليل لا يمنع الإرسال — الخادم يحلّل بشكل نهائيّ.
  void _tryPreviewImportArea() {
    _importedGeometry = null;
    if (_method != 'geojson') return;
    final txt = _geojsonText.text.trim();
    if (txt.isEmpty) return;
    try {
      final decoded = json.decode(txt);
      final geom = _extractPolygon(decoded);
      if (geom != null) setState(() => _importedGeometry = geom);
    } catch (_) {
      // تجاهل — معاينة فقط.
    }
  }

  // استخراج أوّل Polygon من GeoJSON (Polygon / Feature / FeatureCollection).
  Map<String, dynamic>? _extractPolygon(dynamic node) {
    if (node is! Map) return null;
    final type = node['type'];
    if (type == 'Polygon') return node.cast<String, dynamic>();
    if (type == 'Feature') return _extractPolygon(node['geometry']);
    if (type == 'FeatureCollection') {
      final feats = node['features'];
      if (feats is List) {
        for (final f in feats) {
          final g = _extractPolygon(f);
          if (g != null) return g;
        }
      }
    }
    return null;
  }

  // رؤوس المعاينة من geometry مستورَد (للمساحة).
  List<LatLng> _ringToPoints(Map<String, dynamic> geom) {
    final coords = geom['coordinates'];
    if (coords is! List || coords.isEmpty) return const [];
    final ring = coords.first;
    if (ring is! List) return const [];
    final out = <LatLng>[];
    for (final c in ring) {
      if (c is List && c.length >= 2) {
        final lon = (c[0] as num).toDouble();
        final lat = (c[1] as num).toDouble();
        out.add(LatLng(lat, lon));
      }
    }
    return out;
  }

  // المساحة المعروضة حسب الطريقة (هكتار) — تقدير محليّ.
  double get _displayedAreaHa {
    if (_method == 'draw') return _areaHa(_points);
    final g = _importedGeometry;
    if (g != null) return _areaHa(_ringToPoints(g));
    return 0;
  }

  Future<void> _save() async {
    final name = _name.text.trim();
    if (name.isEmpty) {
      setState(() => _step = 0);
      showSnack(context, 'اسم الحقل مطلوب', error: true);
      return;
    }
    if (!_boundaryReady) {
      setState(() => _step = 1);
      showSnack(context, 'حدّد حدّ الحقل أوّلاً (ارسم مضلّعاً مغلقاً أو استورد)',
          error: true);
      return;
    }
    setState(() => _saving = true);
    try {
      Map<String, dynamic> created;
      final manager = _manager.text.trim().isEmpty ? null : _manager.text.trim();
      if (_method == 'geojson') {
        created = await ApiService.instance.importFieldGeoJson(
          _geojsonText.text.trim(),
          name: name,
          crop: _crop,
          soilType: _soilType,
          waterSource: _waterSource,
          manager: manager,
        );
      } else if (_method == 'kml') {
        created = await ApiService.instance.importFieldKml(
          _geojsonText.text.trim(),
          name: name,
          crop: _crop,
          soilType: _soilType,
          waterSource: _waterSource,
          manager: manager,
        );
      } else {
        created = await ApiService.instance.createField(
          name: name,
          geometry: _geometryFromPoints(),
          crop: _crop,
          soilType: _soilType,
          waterSource: _waterSource,
          manager: manager,
        );
      }

      // نوع الريّ ليس ضمن عقد الإنشاء — يُكتب عبر PATCH (ملء تدريجيّ) إن أُدخل.
      final fieldId = created['field_id']?.toString();
      if (_irrigationType != null && fieldId != null && fieldId.isNotEmpty) {
        try {
          await ApiService.instance
              .updateField(fieldId, {'irrigation_type': _irrigationType});
        } catch (_) {
          // عدم حفظ نوع الريّ لا يبطل إنشاء الحقل — نُكمل بنجاح جزئيّ.
        }
      }

      if (!mounted) return;
      showSnack(context, 'تمّ إنشاء الحقل «$name»');
      Navigator.pop(context, true);
    } catch (e) {
      if (!mounted) return;
      setState(() => _saving = false);
      showSnack(context, apiErrorMessage(e), error: true);
    }
  }

  // ── واجهة الخطوات ──
  static const _stepTitles = [
    'اسم الحقل',
    'حدّ الحقل',
    'المحصول',
    'الريّ والمياه',
    'تفاصيل إضافيّة (اختياريّ)',
  ];

  bool get _canAdvance {
    switch (_step) {
      case 0:
        return _name.text.trim().isNotEmpty;
      case 1:
        return _boundaryReady;
      default:
        return true; // الخطوات 2-4 اختياريّة (ملء تدريجيّ)
    }
  }

  void _next() {
    if (_step < _stepTitles.length - 1) {
      setState(() => _step++);
    }
  }

  void _back() {
    if (_step > 0) setState(() => _step--);
  }

  @override
  Widget build(BuildContext context) {
    final isLast = _step == _stepTitles.length - 1;
    return Scaffold(
      backgroundColor: kBg,
      appBar: AppBar(
        backgroundColor: kSurface,
        title: const Text('حقل جديد'),
      ),
      body: SafeArea(
        child: Column(
          children: [
            _progressBar(),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
              child: Align(
                alignment: Alignment.centerRight,
                child: Text(
                  'الخطوة ${_step + 1} من ${_stepTitles.length} · ${_stepTitles[_step]}',
                  style: const TextStyle(
                      color: Colors.white, fontWeight: FontWeight.bold),
                ),
              ),
            ),
            Expanded(child: _stepBody()),
            _navBar(isLast),
          ],
        ),
      ),
    );
  }

  Widget _progressBar() {
    return Row(
      children: List.generate(_stepTitles.length, (i) {
        final done = i <= _step;
        return Expanded(
          child: Container(
            height: 4,
            margin: const EdgeInsets.symmetric(horizontal: 2),
            decoration: BoxDecoration(
              color: done ? kPrimary : Colors.white12,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
        );
      }),
    );
  }

  Widget _stepBody() {
    switch (_step) {
      case 0:
        return _stepName();
      case 1:
        return _stepBoundary();
      case 2:
        return _stepCrop();
      case 3:
        return _stepIrrigation();
      default:
        return _stepAdvanced();
    }
  }

  // الخطوة 1: الاسم.
  Widget _stepName() {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const SectionTitle('سمِّ حقلك'),
        Padding(
          padding: const EdgeInsets.only(top: 12),
          child: TextField(
            controller: _name,
            style: const TextStyle(color: Colors.white),
            decoration: kDec('اسم الحقل'),
            // يُحدِّث حالة زرّ «التالي» مع الكتابة (يعتمد على نصّ غير فارغ).
            onChanged: (_) => setState(() {}),
          ),
        ),
        const SizedBox(height: 8),
        const Text('اسم واضح يسهّل تمييز الحقل لاحقاً.',
            style: TextStyle(color: Colors.grey, fontSize: 12)),
      ],
    );
  }

  // الخطوة 2: اختيار الطريقة + الرسم/الاستيراد.
  Widget _stepBoundary() {
    return Column(
      children: [
        _methodChips(),
        Expanded(
          child: _method == 'draw'
              ? _drawPane()
              : (_method == 'gps' ? _gpsComingSoon() : _importPane()),
        ),
      ],
    );
  }

  Widget _methodChips() {
    Widget chip(String value, IconData icon, String label) {
      final sel = _method == value;
      return Padding(
        padding: const EdgeInsets.symmetric(horizontal: 4),
        child: ChoiceChip(
          selected: sel,
          label: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: 16, color: sel ? Colors.white : Colors.grey),
              const SizedBox(width: 4),
              Text(label),
            ],
          ),
          labelStyle:
              TextStyle(color: sel ? Colors.white : Colors.grey, fontSize: 12),
          selectedColor: kPrimary,
          backgroundColor: kSurface,
          // عند تبديل طريقة الحدود نُصفّر معاينة الهندسة المستوردة كي لا تُستعمَل
          // مساحة GeoJSON قديمة مع طريقة جديدة (رسم/KML).
          onSelected: (_) => setState(() {
            _method = value;
            _importedGeometry = null;
          }),
        ),
      );
    }

    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
      child: Row(
        children: [
          chip('draw', Icons.edit_location_alt, 'رسم'),
          chip('geojson', Icons.code, 'GeoJSON'),
          chip('kml', Icons.public, 'KML'),
          chip('gps', Icons.directions_walk, 'مشي GPS'),
        ],
      ),
    );
  }

  Widget _drawPane() {
    final area = _areaHa(_points);
    return Column(
      children: [
        Expanded(
          child: OfflineFieldMap(
            center: _mapCenter,
            drawingEnabled: true,
            drawingPoints: _points,
            onPolygonChanged: _onPolygonChanged,
          ),
        ),
        Container(
          color: kSurface,
          padding: const EdgeInsets.all(10),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('${_points.length} نقطة',
                        style: const TextStyle(color: Colors.white)),
                    Text(
                      _hasDrawnPolygon
                          ? 'المساحة ≈ ${area.toStringAsFixed(2)} هـ'
                          : 'أضف 3 نقاط على الأقلّ لإغلاق المضلّع',
                      style: TextStyle(
                          color: _hasDrawnPolygon ? kPrimary : Colors.grey,
                          fontSize: 12),
                    ),
                  ],
                ),
              ),
              IconButton(
                tooltip: 'تراجع',
                onPressed: _points.isEmpty ? null : _undoPoint,
                icon: const Icon(Icons.undo, color: Colors.white),
              ),
              IconButton(
                tooltip: 'مسح',
                onPressed: _points.isEmpty ? null : _clearPoints,
                icon: const Icon(Icons.delete_outline, color: Colors.redAccent),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _importPane() {
    final isKml = _method == 'kml';
    final area = _displayedAreaHa;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        SectionTitle(isKml ? 'الصق محتوى ملفّ KML' : 'الصق نصّ GeoJSON'),
        const SizedBox(height: 8),
        Row(
          children: [
            const Spacer(),
            TextButton.icon(
              onPressed: _pasteFromClipboard,
              icon: const Icon(Icons.content_paste, size: 16, color: kPrimary),
              label: const Text('لصق', style: TextStyle(color: kPrimary)),
            ),
          ],
        ),
        TextField(
          controller: _geojsonText,
          maxLines: 8,
          style: const TextStyle(color: Colors.white, fontSize: 12),
          onChanged: (_) {
            _tryPreviewImportArea();
            setState(() {});
          },
          decoration: kDec(isKml
              ? '<Polygon><outerBoundaryIs>…'
              : '{"type":"Polygon","coordinates":[[[lon,lat],…]]}'),
        ),
        const SizedBox(height: 10),
        if (!isKml && _importedGeometry != null && area > 0)
          Text('المساحة ≈ ${area.toStringAsFixed(2)} هـ',
              style: const TextStyle(color: kPrimary, fontSize: 12))
        else if (_geojsonText.text.trim().isNotEmpty)
          const Text('سيتحقّق الخادم من الهندسة عند الحفظ.',
              style: TextStyle(color: Colors.grey, fontSize: 12)),
      ],
    );
  }

  Future<void> _pasteFromClipboard() async {
    final data = await Clipboard.getData(Clipboard.kTextPlain);
    final txt = data?.text;
    if (txt == null || txt.isEmpty) return;
    _geojsonText.text = txt;
    _tryPreviewImportArea();
    setState(() {});
  }

  Widget _gpsComingSoon() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.directions_walk, color: Colors.grey, size: 48),
            const SizedBox(height: 12),
            const Text('المشي بالـGPS لتسجيل الحدّ',
                style: TextStyle(
                    color: Colors.white, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            const Text(
              'قريباً — سيتيح لك السير حول الحقل لتسجيل حدوده آليّاً. حاليّاً '
              'استخدم الرسم أو الاستيراد.',
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.grey, fontSize: 12),
            ),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: () => setState(() => _method = 'draw'),
              style: ElevatedButton.styleFrom(backgroundColor: kPrimary),
              child: const Text('ارسم بدلاً من ذلك'),
            ),
          ],
        ),
      ),
    );
  }

  // الخطوة 3: المحصول.
  Widget _stepCrop() {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const SectionTitle('المحصول الرئيسيّ (اختياريّ)'),
        _dropdown(_crops, _crop, 'المحصول', (v) => setState(() => _crop = v)),
      ],
    );
  }

  // الخطوة 4: مصدر المياه + نوع الريّ.
  Widget _stepIrrigation() {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const SectionTitle('مصدر المياه (اختياريّ)'),
        _dropdown(_waterSources, _waterSource, 'المصدر',
            (v) => setState(() => _waterSource = v)),
        const SizedBox(height: 12),
        const SectionTitle('نوع الريّ (اختياريّ)'),
        _dropdown(_irrigationTypes, _irrigationType, 'نوع الريّ',
            (v) => setState(() => _irrigationType = v)),
      ],
    );
  }

  // الخطوة 5: متقدّم.
  Widget _stepAdvanced() {
    final area = _displayedAreaHa;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const SectionTitle('تفاصيل إضافيّة (اختياريّ)'),
        _dropdown(_soilTypes, _soilType, 'نوع التربة',
            (v) => setState(() => _soilType = v)),
        kField(_manager, 'المسؤول عن الحقل'),
        const SizedBox(height: 16),
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: kSurface,
            borderRadius: BorderRadius.circular(10),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _summaryRow('الاسم', _name.text.trim()),
              _summaryRow(
                  'الحدّ',
                  _method == 'draw'
                      ? '${_points.length} نقطة'
                      : (_method == 'geojson'
                          ? 'GeoJSON مستورَد'
                          : (_method == 'kml' ? 'KML مستورَد' : '—'))),
              if (area > 0)
                _summaryRow('المساحة ≈', '${area.toStringAsFixed(2)} هـ'),
              if (_crop != null) _summaryRow('المحصول', _crops[_crop] ?? _crop!),
              if (_waterSource != null)
                _summaryRow('المياه', _waterSources[_waterSource] ?? _waterSource!),
              if (_irrigationType != null)
                _summaryRow(
                    'الريّ', _irrigationTypes[_irrigationType] ?? _irrigationType!),
            ],
          ),
        ),
      ],
    );
  }

  Widget _summaryRow(String k, String v) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: Row(
          children: [
            Text('$k: ',
                style: const TextStyle(color: Colors.grey, fontSize: 12)),
            Expanded(
              child: Text(v,
                  style: const TextStyle(color: Colors.white, fontSize: 12)),
            ),
          ],
        ),
      );

  Widget _dropdown(Map<String, String> options, String? value, String label,
      ValueChanged<String?> onChanged) {
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: DropdownButtonFormField<String>(
        value: value,
        dropdownColor: kSurface,
        decoration: kDec(label),
        style: const TextStyle(color: Colors.white),
        items: options.entries
            .map((e) => DropdownMenuItem(value: e.key, child: Text(e.value)))
            .toList(),
        onChanged: onChanged,
      ),
    );
  }

  Widget _navBar(bool isLast) {
    return Container(
      color: kSurface,
      padding: const EdgeInsets.all(12),
      child: Row(
        children: [
          if (_step > 0)
            Expanded(
              child: OutlinedButton(
                onPressed: _saving ? null : _back,
                style: OutlinedButton.styleFrom(
                  side: const BorderSide(color: Colors.white24),
                ),
                child: const Text('السابق',
                    style: TextStyle(color: Colors.white)),
              ),
            ),
          if (_step > 0) const SizedBox(width: 12),
          Expanded(
            child: ElevatedButton(
              onPressed: _saving
                  ? null
                  : (isLast
                      ? (_boundaryReady ? _save : null)
                      : (_canAdvance ? _next : null)),
              style: ElevatedButton.styleFrom(backgroundColor: kPrimary),
              child: _saving
                  ? const SizedBox(
                      height: 18,
                      width: 18,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: Colors.white),
                    )
                  : Text(isLast ? 'حفظ الحقل' : 'التالي'),
            ),
          ),
        ],
      ),
    );
  }
}
