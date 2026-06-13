// SAHOOL — lib/screens/field_create_wizard.dart
// معالج إنشاء حقل متعدّد الخطوات (route: 'field_create'). يسدّ أهمّ فجوة:
// إنشاء الحقول الفعليّ. خطوات: (1) الاسم، (2) رسم/استيراد الحدّ على الخريطة،
// (3) المحصول، (4) مصدر المياه + نوع الريّ، (5) متقدّم اختياريّ (نوع التربة/المدير).
// «الملء التدريجيّ»: الخطوات 3-5 اختياريّة عمليّاً؛ الإلزاميّ اسم + مضلّع مغلق.
//
// الرسم يعيد استخدام OfflineFieldMap في وضع drawingEnabled (إضافة نقطة/تراجع/مسح).
// الاستيراد: لصق GeoJSON يعمل فعليّاً؛ KML نصّ يعمل عبر الخادم؛ GPS-walk «قريباً».
// عند الحفظ: createField (أو importFieldGeoJson) ثمّ — إن أُدخل نوع ريّ — updateField
// بـirrigation_type (PATCH). صدق: الخطأ يُعرَض كما هو.
//
// سلسلة الإعداد على نمط Climate FieldView: لا ينتهي المعالج بحفظ الحقل، بل
// «يَستمرّ» إلى خطوات ما بعد الإنشاء المرتبطة بـfield_id الحقيقيّ:
//   إنشاء الحقل (موجود) → موسم (محصول/ريّ/تاريخ بذر) → فحوص تربة (اختياريّ،
//   قابل للتخطّي) → إنتاجيّة (اختياريّ، قابل للتخطّي) → مساحة عمل الحقل.
// الخطوات اللاحقة منظَّمة كقائمة مرتَّبة (_postSteps) قابلة للتوسّع: تُضاف خطوة
// جديدة بإلحاق عنصر دون إعادة توصيل التنقّل. كلّها على نقاط API فعليّة في
// api_service.dart؛ ما لا تتوفّر له واجهة يبقى اختياريّاً/قابلاً للتخطّي.
import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:latlong2/latlong.dart';

import '../services/api_service.dart';
import '../widgets/form_kit.dart';
import '../widgets/offline_field_map.dart';
import '../widgets/state_views.dart';
import 'field_workspace_screen.dart';

/// مرحلة المعالج: إنشاء الحقل (الخطوات الأصليّة) ثمّ سلسلة الإعداد بعد الحفظ.
enum _WizardPhase { create, postCreate }

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

  // ── حالة سلسلة الإعداد بعد الحفظ (FieldView-style) ──
  _WizardPhase _phase = _WizardPhase.create;
  String? _createdFieldId; // معرّف الحقل المُنشأ (مصدر الحقيقة لخطوات ما بعد)
  double? _createdAreaHa; // المساحة من استجابة الخادم (area_ha) إن توفّرت
  int _postStep = 0; // مؤشّر داخل _postSteps

  // خطوة الموسم: محصول + ريّ (يُعاد استخدام مفردات الإنشاء) + تاريخ بذر + هدف.
  String? _seasonCrop;
  String? _seasonIrrigation;
  DateTime? _sowingDate;
  final _cultivar = TextEditingController();
  final _targetYield = TextEditingController(); // كغ/هـ

  // خطوة فحوص التربة (اختياريّة): pH / مادّة عضويّة / CEC داخل result.
  final _soilPh = TextEditingController();
  final _soilOm = TextEditingController(); // % مادّة عضويّة
  final _soilCec = TextEditingController();
  final _soilLabName = TextEditingController();
  DateTime? _sampledOn;

  // خطوة الإنتاجيّة (اختياريّة): أيّام النموّ + متوسّط NDVI.
  final _daysInGrowing = TextEditingController();
  final _avgNdvi = TextEditingController();
  Map<String, dynamic>? _yieldResult; // نتيجة آخر تقدير (للعرض)

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
    _cultivar.dispose();
    _targetYield.dispose();
    _soilPh.dispose();
    _soilOm.dispose();
    _soilCec.dispose();
    _soilLabName.dispose();
    _daysInGrowing.dispose();
    _avgNdvi.dispose();
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
      if (c is List && c.length >= 2 && c[0] is num && c[1] is num) {
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

      // ── الانتقال إلى سلسلة الإعداد بدل إغلاق المعالج (نمط FieldView) ──
      // إن نقص field_id (شكل استجابة غير متوقّع) نتراجع للسلوك القديم: نُغلق
      // بنجاح كي لا نعلّق المستخدم — صدق: لا خطوات مرتبطة بمعرّف غائب.
      if (fieldId == null || fieldId.isEmpty) {
        Navigator.pop(context, true);
        return;
      }

      // مساحة من الخادم (area_ha) إن توفّرت — حارس شكل: رقم فقط.
      final areaRaw = created['area_ha'];
      final areaHa = areaRaw is num ? areaRaw.toDouble() : null;

      setState(() {
        _saving = false;
        _createdFieldId = fieldId;
        _createdAreaHa = areaHa;
        // تهيئة خطوة الموسم من اختيارات الإنشاء (لا تكرار إدخال).
        _seasonCrop = _crop;
        _seasonIrrigation = _irrigationType;
        _phase = _WizardPhase.postCreate;
        _postStep = 0;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _saving = false);
      showSnack(context, apiErrorMessage(e), error: true);
    }
  }

  // ── سلسلة الإعداد بعد الإنشاء (قائمة مرتَّبة قابلة للتوسّع) ──
  // كلّ خطوة تعرّف: العنوان، الجسم، هل هي قابلة للتخطّي، ودالّة الإرسال (تُعيد
  // true عند النجاح كي يتقدّم التنقّل). لإضافة خطوة لاحقاً: ألحِق _PostStep جديداً.
  List<_PostStep> get _postSteps => [
        _PostStep(
          title: 'الموسم',
          builder: _stepSeason,
          skippable: false, // الموسم أساس الإعداد (لكنّه يتطلّب محصولاً فقط)
          submit: _submitSeason,
          canSubmit: () => _seasonCrop != null,
        ),
        _PostStep(
          title: 'فحوص التربة (اختياريّ)',
          builder: _stepSoilTests,
          skippable: true,
          submit: _submitSoilTest,
          // إرسال فقط إن أُدخلت قيمة واحدة على الأقلّ، وإلّا فالأفضل التخطّي.
          canSubmit: () =>
              _hasNum(_soilPh) || _hasNum(_soilOm) || _hasNum(_soilCec),
        ),
        _PostStep(
          title: 'تقدير الإنتاجيّة (اختياريّ)',
          builder: _stepYield,
          skippable: true,
          submit: _submitYield,
          canSubmit: () => _seasonCrop != null, // التقدير يحتاج محصولاً
        ),
      ];

  bool _hasNum(TextEditingController c) => _parseNum(c.text) != null;

  // محلّل رقم متسامح (يقبل فارغاً/نصّاً غير رقميّ بإرجاع null — دفاعيّ).
  num? _parseNum(String s) {
    final t = s.trim();
    if (t.isEmpty) return null;
    return num.tryParse(t);
  }

  String _ymd(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-'
      '${d.month.toString().padLeft(2, '0')}-'
      '${d.day.toString().padLeft(2, '0')}';

  Future<DateTime?> _pickDate(DateTime? initial) => showDatePicker(
        context: context,
        initialDate: initial ?? DateTime.now(),
        firstDate: DateTime(2015),
        lastDate: DateTime(2100),
      );

  // إنشاء الموسم على نقطة فعليّة. يتطلّب محصولاً (يُرسَل ضمن crops).
  Future<bool> _submitSeason() async {
    final fid = _createdFieldId;
    final crop = _seasonCrop;
    if (fid == null || crop == null) return false;
    await ApiService.instance.createSeason(
      fid,
      crop: crop,
      cultivar: _cultivar.text.trim().isEmpty ? null : _cultivar.text.trim(),
      irrigationType: _seasonIrrigation,
      sowingDate: _sowingDate != null ? _ymd(_sowingDate!) : null,
      targetYieldKgHa: _parseNum(_targetYield.text),
    );
    return true;
  }

  // فحص تربة اختياريّ — pH/OM/CEC داخل result. يُرسَل فقط إن وُجدت قيمة.
  Future<bool> _submitSoilTest() async {
    final fid = _createdFieldId;
    if (fid == null) return false;
    await ApiService.instance.submitSoilLabTest(
      fid,
      labName:
          _soilLabName.text.trim().isEmpty ? null : _soilLabName.text.trim(),
      sampledOn: _sampledOn != null ? _ymd(_sampledOn!) : null,
      ph: _parseNum(_soilPh.text),
      organicMatter: _parseNum(_soilOm.text),
      cec: _parseNum(_soilCec.text),
    );
    return true;
  }

  // تقدير إنتاجيّة اختياريّ — يحتاج محصولاً. نعرض النتيجة (حارس شكل) ولا نتقدّم
  // آليّاً كي يطّلع المستخدم؛ يضغط «إلى مساحة العمل» بعدها.
  Future<bool> _submitYield() async {
    final fid = _createdFieldId;
    final crop = _seasonCrop;
    if (fid == null || crop == null) return false;
    final res = await ApiService.instance.requestYieldEstimate(
      fid,
      crop: crop,
      daysInGrowing: _parseNum(_daysInGrowing.text)?.toInt(),
      avgNdviGrowing: _parseNum(_avgNdvi.text),
    );
    setState(() => _yieldResult = res);
    return true;
  }

  // تقدّم/تخطّي خطوة ما بعد الإنشاء. عند نهاية القائمة ⇒ مساحة عمل الحقل.
  Future<void> _postNext({required bool skip}) async {
    final steps = _postSteps;
    final step = steps[_postStep];
    if (!skip) {
      setState(() => _saving = true);
      try {
        final ok = await step.submit();
        if (!mounted) return;
        if (!ok) {
          setState(() => _saving = false);
          showSnack(context, 'تعذّر إكمال الخطوة', error: true);
          return;
        }
      } catch (e) {
        if (!mounted) return;
        setState(() => _saving = false);
        showSnack(context, apiErrorMessage(e), error: true);
        return;
      }
      if (!mounted) return;
      setState(() => _saving = false);
    }
    if (_postStep < steps.length - 1) {
      setState(() => _postStep++);
    } else {
      _goToWorkspace();
    }
  }

  void _postBack() {
    if (_postStep > 0) setState(() => _postStep--);
  }

  // الانتقال إلى مساحة عمل الحقل المُنشأ، مع إعلام القائمة الخلفيّة بالنجاح.
  // نستبدل المعالج بمساحة العمل (لا نُكدّس) ونعتمد على pushNamed كي يربطه
  // main.dart. نمرّر معرّف الحقل كوسيط (يقبله FieldWorkspaceScreen).
  void _goToWorkspace() {
    final fid = _createdFieldId;
    final nav = Navigator.of(context);
    // أغلق المعالج (يردّ true لإعادة تحميل قائمة الحقول) ثمّ افتح مساحة العمل.
    nav.pop(true);
    if (fid != null && fid.isNotEmpty) {
      try {
        nav.pushNamed(FieldWorkspaceScreen.routeName, arguments: fid);
      } catch (_) {
        // المسار قد لا يكون مسجَّلاً في بيئات معيّنة — الإغلاق بنجاح يكفي.
      }
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
    // مرحلة ما بعد الإنشاء: نعرض سلسلة الإعداد (موسم/تربة/إنتاجيّة) بدل خطوات الإنشاء.
    if (_phase == _WizardPhase.postCreate) return _buildPostCreate();

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
            _progressBar(_stepTitles.length, _step),
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

  // ── واجهة سلسلة الإعداد بعد الإنشاء (FieldView-style) ──
  // شريط تقدّم متّسق مع معالج الإنشاء، عنوان الخطوة، الجسم، ثمّ شريط تنقّل فيه
  // «رجوع» (إن لم نكن في أوّل خطوة) و«تخطّي» (للخطوات الاختياريّة) و«التالي/إنهاء».
  Widget _buildPostCreate() {
    final steps = _postSteps;
    final step = steps[_postStep];
    final isLast = _postStep == steps.length - 1;
    return Scaffold(
      backgroundColor: kBg,
      appBar: AppBar(
        backgroundColor: kSurface,
        title: const Text('إعداد الحقل'),
        automaticallyImplyLeading: false,
      ),
      body: SafeArea(
        child: Column(
          children: [
            _progressBar(steps.length, _postStep),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
              child: Align(
                alignment: Alignment.centerRight,
                child: Text(
                  'الخطوة ${_postStep + 1} من ${steps.length} · ${step.title}',
                  style: const TextStyle(
                      color: Colors.white, fontWeight: FontWeight.bold),
                ),
              ),
            ),
            Expanded(child: step.builder()),
            _postNavBar(step, isLast),
          ],
        ),
      ),
    );
  }

  Widget _postNavBar(_PostStep step, bool isLast) {
    // زرّ الإجراء الأساسيّ مُعطَّل إن لم تتحقّق شروط الإرسال (مثل غياب المحصول).
    final canSubmit = step.canSubmit();
    return Container(
      color: kSurface,
      padding: const EdgeInsets.all(12),
      child: Row(
        children: [
          if (_postStep > 0)
            Expanded(
              child: OutlinedButton(
                onPressed: _saving ? null : _postBack,
                style: OutlinedButton.styleFrom(
                  side: const BorderSide(color: Colors.white24),
                ),
                child: const Text('رجوع',
                    style: TextStyle(color: Colors.white)),
              ),
            ),
          if (_postStep > 0) const SizedBox(width: 12),
          if (step.skippable)
            Expanded(
              child: OutlinedButton(
                onPressed: _saving ? null : () => _postNext(skip: true),
                style: OutlinedButton.styleFrom(
                  side: const BorderSide(color: Colors.white24),
                ),
                child: const Text('تخطّي',
                    style: TextStyle(color: Colors.white)),
              ),
            ),
          if (step.skippable) const SizedBox(width: 12),
          Expanded(
            child: ElevatedButton(
              onPressed: (_saving || !canSubmit)
                  ? null
                  : () => _postNext(skip: false),
              style: ElevatedButton.styleFrom(backgroundColor: kPrimary),
              child: _saving
                  ? const SizedBox(
                      height: 18,
                      width: 18,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: Colors.white),
                    )
                  : Text(isLast ? 'إلى مساحة العمل' : 'التالي'),
            ),
          ),
        ],
      ),
    );
  }

  // شريط تقدّم عامّ يُعاد استخدامه لمرحلتي الإنشاء وما بعده ([total] خطوات،
  // الحاليّة [current] صفريّة الأساس).
  Widget _progressBar(int total, int current) {
    return Row(
      children: List.generate(total, (i) {
        final done = i <= current;
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

  // ── أجسام خطوات ما بعد الإنشاء ──

  // بطاقة معلومات الحقل المُنشأ (تظهر أعلى كلّ خطوة لربط السياق بصريّاً).
  Widget _createdFieldBanner() {
    final area = _createdAreaHa;
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: kSurface,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        children: [
          const Icon(Icons.check_circle, color: kPrimary, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('تمّ إنشاء «${_name.text.trim()}»',
                    style: const TextStyle(
                        color: Colors.white, fontWeight: FontWeight.bold)),
                Text(
                  area != null
                      ? 'المساحة ≈ ${area.toStringAsFixed(2)} هـ'
                      : 'أكمِل إعداد الحقل بالخطوات التالية',
                  style: const TextStyle(color: Colors.grey, fontSize: 12),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // مُحدِّد تاريخ موحّد (يعرض القيمة المختارة أو نائباً، ويفتح منتقي التاريخ).
  Widget _dateField(String label, DateTime? value, ValueChanged<DateTime> onPick) {
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: InkWell(
        onTap: () async {
          final picked = await _pickDate(value);
          if (picked != null) onPick(picked);
        },
        child: InputDecorator(
          decoration: kDec(label),
          child: Text(
            value != null ? _ymd(value) : 'اختر تاريخاً',
            style: TextStyle(
                color: value != null ? Colors.white : Colors.grey),
          ),
        ),
      ),
    );
  }

  // الخطوة (ما بعد): الموسم — محصول + ريّ (مفردات الإنشاء نفسها) + تاريخ بذر + هدف.
  Widget _stepSeason() {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _createdFieldBanner(),
        const SectionTitle('موسم الحقل'),
        const Text('عرّف ما يُزرَع هذا الموسم — أساس التوصيات لاحقاً.',
            style: TextStyle(color: Colors.grey, fontSize: 12)),
        _dropdown(_crops, _seasonCrop, 'المحصول (مطلوب)',
            (v) => setState(() => _seasonCrop = v)),
        _dropdown(_irrigationTypes, _seasonIrrigation, 'نوع الريّ (اختياريّ)',
            (v) => setState(() => _seasonIrrigation = v)),
        kField(_cultivar, 'الصنف/الهجين (اختياريّ)'),
        _dateField('تاريخ البذر (اختياريّ)', _sowingDate,
            (d) => setState(() => _sowingDate = d)),
        kField(_targetYield, 'الإنتاجيّة المستهدفة كغ/هـ (اختياريّ)',
            number: true),
      ],
    );
  }

  // الخطوة (ما بعد): فحوص التربة — pH/مادّة عضويّة/CEC داخل result. اختياريّة كلّيّاً.
  Widget _stepSoilTests() {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _createdFieldBanner(),
        const SectionTitle('فحوص التربة (اختياريّ)'),
        const Text(
            'أدخِل نتائج فحص مخبريّ إن توفّرت، أو تخطَّ هذه الخطوة وأضِفها لاحقاً.',
            style: TextStyle(color: Colors.grey, fontSize: 12)),
        kField(_soilPh, 'الحموضة pH', number: true),
        kField(_soilOm, 'المادّة العضويّة % (organic matter)', number: true),
        kField(_soilCec, 'السعة التبادليّة CEC', number: true),
        kField(_soilLabName, 'اسم المختبر (اختياريّ)'),
        _dateField('تاريخ أخذ العيّنة (اختياريّ)', _sampledOn,
            (d) => setState(() => _sampledOn = d)),
      ],
    );
  }

  // الخطوة (ما بعد): تقدير الإنتاجيّة — يحتاج محصولاً. اختياريّة وقابلة للتخطّي.
  Widget _stepYield() {
    final res = _yieldResult;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _createdFieldBanner(),
        const SectionTitle('تقدير الإنتاجيّة (اختياريّ)'),
        const Text(
            'تقدير مبدئيّ للإنتاجيّة بناءً على المحصول وعمر النموّ ومؤشّر NDVI.',
            style: TextStyle(color: Colors.grey, fontSize: 12)),
        kField(_daysInGrowing, 'أيّام النموّ (اختياريّ)', number: true),
        kField(_avgNdvi, 'متوسّط NDVI (اختياريّ)', number: true),
        if (res != null) ...[
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
                const Text('نتيجة التقدير',
                    style: TextStyle(
                        color: Colors.white, fontWeight: FontWeight.bold)),
                const SizedBox(height: 6),
                Text(_yieldSummary(res),
                    style: const TextStyle(color: kPrimary, fontSize: 13)),
              ],
            ),
          ),
        ],
      ],
    );
  }

  // ملخّص نتيجة الإنتاجيّة بحارس شكل (مفاتيح قد تختلف؛ نقرأ المتوقَّع دفاعيّاً).
  String _yieldSummary(Map<String, dynamic> res) {
    final est = res['estimated_yield_kg_ha'] ??
        res['yield_kg_ha'] ??
        res['estimate'];
    if (est is num) {
      return 'الإنتاجيّة المقدَّرة ≈ ${est.toStringAsFixed(0)} كغ/هـ';
    }
    final conf = res['confidence'];
    if (conf != null) return 'تمّ التقدير (ثقة: $conf).';
    return 'تمّ استلام التقدير من الخادم.';
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

/// خطوة واحدة في سلسلة الإعداد بعد الإنشاء (FieldView-style). القائمة المرتَّبة
/// (_postSteps) من هذا النوع قابلة للتوسّع: تُضاف خطوة بإلحاق عنصر دون إعادة
/// توصيل التنقّل. [submit] تُعيد true عند النجاح كي يتقدّم المعالج؛ [skippable]
/// يُظهر زرّ «تخطّي»؛ [canSubmit] يُفعِّل/يُعطِّل زرّ الإجراء الأساسيّ.
class _PostStep {
  final String title;
  final Widget Function() builder;
  final bool skippable;
  final Future<bool> Function() submit;
  final bool Function() canSubmit;
  const _PostStep({
    required this.title,
    required this.builder,
    required this.skippable,
    required this.submit,
    required this.canSubmit,
  });
}
