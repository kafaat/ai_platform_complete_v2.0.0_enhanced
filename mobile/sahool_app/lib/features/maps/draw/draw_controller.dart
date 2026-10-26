// SAHOOL — features/maps/draw/draw_controller.dart
// حالة رسم حدّ الحقل: الوضع، الهندسة، التراجع/الإعادة، تحرير الرؤوس، والالتقاط.
//
// علّة قديمة أُصلحت هنا: كان المعالج يحفظ رؤوس الدائرة (48 رأساً) في قائمة النقاط
// نفسها، فإذا بُدِّل الوضع إلى «نقاط» أضافت النقرة التالية رأساً تاسعاً وأربعين،
// و«تراجع» يحذف رأساً من الدائرة فيشوّهها. الآن لكلّ وضعٍ هندسته الخاصّة (مضلّع:
// رؤوس، مستطيل: زاويتان، محور: مركز + نصف قطر، نقطة: موقع واحد)، والحلقة
// **مشتقّة** منها لا مخزّنة؛ وتبديل الوضع يبدأ هندسةً فارغة، والتراجع يعيد لقطة
// الحالة كاملةً (الوضع مع هندسته) لا رأساً واحداً.
//
// وضع «نقطة» يحدّد موقعاً واحداً (مثل بئر أو نقطة استكشاف) وليس حدّاً: حلقته
// فارغة، فلا يقدّمه معالج الحقل.
import 'package:flutter/foundation.dart';
import 'package:latlong2/latlong.dart';

import 'boundary_validation.dart';
import 'geo_measure.dart';
import 'snapping.dart';

enum DrawMode { polygon, rectangle, circle, point }

/// لقطة ثابتة لحالة الرسم (وحدة التراجع/الإعادة).
@immutable
class DrawSnapshot {
  const DrawSnapshot({
    this.mode = DrawMode.polygon,
    this.vertices = const [],
    this.cornerA,
    this.cornerB,
    this.center,
    this.radiusM,
    this.point,
  });

  final DrawMode mode;
  final List<LatLng> vertices;
  final LatLng? cornerA;
  final LatLng? cornerB;
  final LatLng? center;
  final double? radiusM;
  final LatLng? point;
}

class DrawController extends ChangeNotifier {
  DrawController({DrawMode mode = DrawMode.polygon, this.historyLimit = 200})
    : _s = DrawSnapshot(mode: mode);

  final int historyLimit;
  DrawSnapshot _s;
  final List<DrawSnapshot> _undo = [];
  final List<DrawSnapshot> _redo = [];
  bool _editing = false;

  /// يزداد مع كلّ تغيير؛ يصلح مفتاحاً لذاكرة التحقّق.
  int revision = 0;

  /// يزداد حين يجب أن تؤطّر الخريطة الحدّ (استيراد، GPS).
  int fitRequest = 0;

  /// حلقات الحقول القائمة: للالتقاط وللتحقّق من التداخل.
  List<ExistingField> _existing = const [];
  List<ExistingField> get existingFields => _existing;
  set existingFields(List<ExistingField> v) {
    _existing = v;
    _validation = null;
    notifyListeners();
  }

  bool snapEnabled = true;

  /// مصدر رؤوس المضلّع: manual | gps | import_geojson | import_kml.
  String polygonSource = 'manual';

  /// مصدر الحدّ لـ`boundary_metadata.source` في طلب الإنشاء.
  String get boundarySource => switch (_s.mode) {
    DrawMode.rectangle => 'rectangle',
    DrawMode.circle => 'pivot',
    DrawMode.point => 'point',
    DrawMode.polygon => polygonSource,
  };

  /// آخر التقاط (للعرض: «التُقِط لرأس حقل مجاور»).
  SnapKind lastSnap = SnapKind.none;

  /// الرأس المحدَّد (لزرّ «حذف الرأس» البديل عن الضغط المطوّل).
  int? selectedVertex;

  // ── القراءة ──
  DrawSnapshot get snapshot => _s;
  DrawMode get mode => _s.mode;
  List<LatLng> get vertices => List.unmodifiable(_s.vertices);
  LatLng? get cornerA => _s.cornerA;
  LatLng? get cornerB => _s.cornerB;
  LatLng? get center => _s.center;
  double? get radiusM => _s.radiusM;
  LatLng? get point => _s.point;
  bool get canUndo => _undo.isNotEmpty;
  bool get canRedo => _redo.isNotEmpty;

  /// الحلقة الخارجيّة المفتوحة المشتقّة من هندسة الوضع الحاليّ.
  List<LatLng> get ring {
    switch (_s.mode) {
      case DrawMode.polygon:
        return List.unmodifiable(_s.vertices);
      case DrawMode.rectangle:
        final a = _s.cornerA, b = _s.cornerB;
        if (a == null || b == null) return const [];
        return [
          a,
          LatLng(a.latitude, b.longitude),
          b,
          LatLng(b.latitude, a.longitude),
        ];
      case DrawMode.circle:
        final c = _s.center, r = _s.radiusM;
        if (c == null || r == null || r <= 0) return const [];
        return pivotPolygon(c, r);
      case DrawMode.point:
        return const [];
    }
  }

  /// الرؤوس القابلة للسحب (مضلّع أو زوايا المستطيل المكتمل).
  List<LatLng> get editableVertices => switch (_s.mode) {
    DrawMode.polygon => vertices,
    DrawMode.rectangle => ring,
    _ => const [],
  };

  /// نقاط منتصف الأضلاع (سحبها يُدرج رأساً).
  List<LatLng> get midpoints {
    final r = editableVertices;
    if (r.length < 2) return const [];
    final n = r.length >= 3 ? r.length : r.length - 1;
    return [
      for (var i = 0; i < n; i++)
        LatLng(
          (r[i].latitude + r[(i + 1) % r.length].latitude) / 2,
          (r[i].longitude + r[(i + 1) % r.length].longitude) / 2,
        ),
    ];
  }

  bool get isPivot =>
      _s.mode == DrawMode.circle && _s.center != null && (_s.radiusM ?? 0) > 0;

  /// معاملات المحور القانونيّة كما يرسلها الويب (`makePivotPayload`) ويقرؤها
  /// الخادم (`pivot_spec_from_payload`). null لغير المحور.
  Map<String, dynamic>? get pivotPayload {
    if (!isPivot) return null;
    return {
      'center': {
        'lon': pyRound(_s.center!.longitude, 7),
        'lat': pyRound(_s.center!.latitude, 7),
      },
      'radius_m': pyRound(_s.radiusM!, 2),
      'start_angle_deg': 0,
      'end_angle_deg': 360,
      'vertices': kPivotVertices,
    };
  }

  /// GeoJSON Polygon مغلق بترتيب [lon,lat] (null إن لم تكتمل الحلقة).
  Map<String, dynamic>? get geometry {
    final r = ring;
    if (r.length < 3) return null;
    final coords = [
      for (final p in r) [p.longitude, p.latitude],
    ];
    coords.add([r.first.longitude, r.first.latitude]);
    return {
      'type': 'Polygon',
      'coordinates': [coords],
    };
  }

  BoundaryValidation? _validation;
  int _validationRev = -1;

  /// تحقّق الحدّ الحاليّ (مُخزَّن حتّى التغيير التالي).
  BoundaryValidation get validation {
    if (_validation == null || _validationRev != revision) {
      _validation = validateBoundary(ring, existing: _existing);
      _validationRev = revision;
    }
    return _validation!;
  }

  double get perimeter => perimeterM(ring);

  // ── الكتابة ──
  void _commit(DrawSnapshot next) {
    _undo.add(_s);
    if (_undo.length > historyLimit) _undo.removeAt(0);
    _redo.clear();
    _apply(next);
  }

  void _apply(DrawSnapshot next) {
    _s = next;
    revision++;
    if (selectedVertex != null && selectedVertex! >= editableVertices.length) {
      selectedVertex = null;
    }
    notifyListeners();
  }

  void undo() {
    if (_undo.isEmpty) return;
    _redo.add(_s);
    selectedVertex = null;
    _apply(_undo.removeLast());
  }

  void redo() {
    if (_redo.isEmpty) return;
    _undo.add(_s);
    selectedVertex = null;
    _apply(_redo.removeLast());
  }

  /// يبدّل الوضع ويبدأ هندسةً فارغة (يمكن التراجع عنه).
  void setMode(DrawMode m) {
    if (m == _s.mode) return;
    selectedVertex = null;
    _commit(DrawSnapshot(mode: m));
  }

  /// يمسح هندسة الوضع الحاليّ (يمكن التراجع عنه).
  void clear() {
    if (ring.isEmpty &&
        _s.cornerA == null &&
        _s.center == null &&
        _s.point == null) {
      return;
    }
    selectedVertex = null;
    _commit(DrawSnapshot(mode: _s.mode));
  }

  LatLng _snap(
    LatLng p,
    double toleranceM, {
    List<List<LatLng>> extra = const [],
  }) {
    if (!snapEnabled || toleranceM <= 0) {
      lastSnap = SnapKind.none;
      return p;
    }
    final targets = [for (final f in _existing) ...f.rings, ...extra];
    final r = snapPoint(p, targets, toleranceM: toleranceM);
    lastSnap = r.kind;
    return r.point;
  }

  /// نقرة على الخريطة؛ سلوكها بحسب الوضع. [snapToleranceM]: تسامح الالتقاط.
  void tap(LatLng p, {double snapToleranceM = 0}) {
    switch (_s.mode) {
      case DrawMode.polygon:
        final v = _s.vertices;
        // نقرة قرب الرأس الأوّل تُغلق المضلّع ولا تضيف رأساً مكرّراً.
        final q = _snap(
          p,
          snapToleranceM,
          extra: v.length >= 3
              ? [
                  [v.first],
                ]
              : const [],
        );
        if (v.length >= 3 && q == v.first) return;
        if (v.isEmpty) polygonSource = 'manual';
        _commit(DrawSnapshot(mode: DrawMode.polygon, vertices: [...v, q]));
      case DrawMode.rectangle:
        final q = _snap(p, snapToleranceM);
        if (_s.cornerA == null || _s.cornerB != null) {
          _commit(DrawSnapshot(mode: DrawMode.rectangle, cornerA: q));
        } else {
          _commit(
            DrawSnapshot(
              mode: DrawMode.rectangle,
              cornerA: _s.cornerA,
              cornerB: q,
            ),
          );
        }
      case DrawMode.circle:
        _commit(
          DrawSnapshot(mode: DrawMode.circle, center: p, radiusM: _s.radiusM),
        );
      case DrawMode.point:
        _commit(DrawSnapshot(mode: DrawMode.point, point: p));
    }
  }

  /// يضبط نصف قطر المحور بالأمتار (≤0 يُتجاهَل).
  void setRadius(double meters) {
    if (_s.mode != DrawMode.circle || !(meters > 0)) return;
    if (meters == _s.radiusM) return;
    _commit(
      DrawSnapshot(mode: DrawMode.circle, center: _s.center, radiusM: meters),
    );
  }

  /// يضيف رأساً مباشرةً (GPS) في وضع المضلّع.
  void addVertex(LatLng p) {
    if (_s.mode != DrawMode.polygon || _s.vertices.isEmpty) {
      polygonSource = 'gps';
    }
    if (_s.mode != DrawMode.polygon) {
      _commit(DrawSnapshot(mode: DrawMode.polygon, vertices: [p]));
      return;
    }
    _commit(
      DrawSnapshot(mode: DrawMode.polygon, vertices: [..._s.vertices, p]),
    );
  }

  /// يحمّل حلقةً جاهزة (استيراد) في وضع المضلّع ويطلب تأطير الخريطة.
  void loadRing(List<LatLng> r, {String source = 'manual'}) {
    polygonSource = source;
    final pts = [...r];
    if (pts.length > 1 && pts.first == pts.last) pts.removeLast();
    selectedVertex = null;
    fitRequest++;
    _commit(DrawSnapshot(mode: DrawMode.polygon, vertices: pts));
  }

  /// يحوّل المستطيل المكتمل إلى مضلّع حرّ (لتحرير زاوية بمفردها).
  List<LatLng> _editableAsPolygon() =>
      _s.mode == DrawMode.rectangle ? ring : [..._s.vertices];

  bool get _vertexEditable =>
      _s.mode == DrawMode.polygon ||
      (_s.mode == DrawMode.rectangle && ring.isNotEmpty);

  void deleteVertex(int i) {
    if (!_vertexEditable) return;
    final v = _editableAsPolygon();
    if (i < 0 || i >= v.length) return;
    v.removeAt(i);
    selectedVertex = null;
    _commit(DrawSnapshot(mode: DrawMode.polygon, vertices: v));
  }

  void insertVertex(int afterIndex, LatLng p) {
    if (!_vertexEditable) return;
    final v = _editableAsPolygon();
    if (afterIndex < 0 || afterIndex >= v.length) return;
    v.insert(afterIndex + 1, p);
    _commit(DrawSnapshot(mode: DrawMode.polygon, vertices: v));
  }

  void moveVertex(int i, LatLng p, {double snapToleranceM = 0}) {
    beginEdit();
    updateVertex(i, p, snapToleranceM: snapToleranceM);
    endEdit();
  }

  // ── السحب: لقطة تراجع واحدة لكلّ سحبة، لا لكلّ إطار ──
  void beginEdit() {
    if (_editing) return;
    _editing = true;
    _undo.add(_s);
    if (_undo.length > historyLimit) _undo.removeAt(0);
    _redo.clear();
  }

  void endEdit() {
    _editing = false;
  }

  void updateVertex(int i, LatLng p, {double snapToleranceM = 0}) {
    if (!_vertexEditable) return;
    final v = _editableAsPolygon();
    if (i < 0 || i >= v.length) return;
    v[i] = _snap(p, snapToleranceM);
    selectedVertex = i;
    _apply(DrawSnapshot(mode: DrawMode.polygon, vertices: v));
  }

  /// يُدرج رأساً عند منتصف الضلع [edge] ويعيد فهرسه (لمتابعة السحب).
  int beginInsertAt(int edge, LatLng p) {
    beginEdit();
    final v = _editableAsPolygon();
    v.insert(edge + 1, p);
    _apply(DrawSnapshot(mode: DrawMode.polygon, vertices: v));
    return edge + 1;
  }

  void updateCenter(LatLng p) {
    if (_s.mode != DrawMode.circle) return;
    _apply(DrawSnapshot(mode: DrawMode.circle, center: p, radiusM: _s.radiusM));
  }

  /// نصف القطر من موقع مقبض الحافّة.
  void updateRadiusFrom(LatLng edgePoint) {
    final c = _s.center;
    if (_s.mode != DrawMode.circle || c == null) return;
    final r = haversineM(c, edgePoint, earthRadiusM: kPivotEarthRadiusM);
    if (r <= 0) return;
    _apply(DrawSnapshot(mode: DrawMode.circle, center: c, radiusM: r));
  }

  void selectVertex(int? i) {
    selectedVertex = i;
    notifyListeners();
  }
}
