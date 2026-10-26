// SAHOOL — features/maps/presentation/widgets/sahool_map_controller.dart
// التحكّم بكاميرا [SahoolMap] من الحالة: هدف عرض تصريحيّ ([MapViewTarget]) تتبعه
// الكاميرا كلّما تغيّر، ومتحكّم أوامريّ ([SahoolMapController]) للتأطير والتحريك.
//
// الخلل الذي يسدّه: الودجت القديم مرّر initialCenter فقط بلا MapController ولا
// didUpdateWidget، فلم تتحرّك الكاميرا حين تغيّر المركز (نقاط GPS خارج الشاشة
// تبقى مخفيّة). هنا الأوامر قبل جاهزيّة الخريطة تُصفّ وتُنفَّذ عند onMapReady.
import 'package:flutter/widgets.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import '../../geo/geo_json.dart';

/// حدود اليمن كما يعرّفها الخادم (geospatial_integrity.py: YEMEN_BBOX) — العرض
/// الافتراضيّ بدل نقطة ثابتة في الصحراء.
final LatLngBounds kYemenBounds = LatLngBounds(
  const LatLng(12.0, 41.5),
  const LatLng(19.0, 54.5),
);

/// التكبير عند تأطير نقطة واحدة/حدود متحلّلة.
const double kSinglePointZoom = 16;

/// هدف عرض تصريحيّ. يُقارَن بالقيمة: تغيّره ⇒ تتحرّك الكاميرا.
@immutable
class MapViewTarget {
  const MapViewTarget.center(LatLng this.center, {this.zoom = kSinglePointZoom})
    : bounds = null,
      padding = EdgeInsets.zero,
      maxZoom = null;

  const MapViewTarget.bounds(
    LatLngBounds this.bounds, {
    this.padding = const EdgeInsets.all(48),
    this.maxZoom = 18,
  }) : center = null,
       zoom = null;

  /// يؤطّر هندسة؛ null إن كانت فارغة.
  static MapViewTarget? geometry(
    FieldGeometry? g, {
    EdgeInsets padding = const EdgeInsets.all(48),
  }) {
    final b = g?.bounds;
    return b == null ? null : MapViewTarget.bounds(b, padding: padding);
  }

  /// يؤطّر نقاطاً؛ نقطة واحدة ⇒ مركز بتكبير قريب.
  static MapViewTarget? points(
    Iterable<LatLng> pts, {
    EdgeInsets padding = const EdgeInsets.all(48),
  }) {
    final list = pts.toList();
    if (list.isEmpty) return null;
    return MapViewTarget.bounds(
      LatLngBounds.fromPoints(list),
      padding: padding,
    );
  }

  final LatLng? center;
  final double? zoom;
  final LatLngBounds? bounds;
  final EdgeInsets padding;
  final double? maxZoom;

  bool get _degenerate {
    final b = bounds;
    return b != null && b.south == b.north && b.east == b.west;
  }

  /// للتهيئة الأولى لـMapOptions.
  CameraFit? get cameraFit => (bounds == null || _degenerate)
      ? null
      : CameraFit.bounds(bounds: bounds!, padding: padding, maxZoom: maxZoom);
  LatLng get initialCenter => center ?? bounds!.center;
  double get initialZoom => zoom ?? kSinglePointZoom;

  /// يطبّق الهدف على متحكّم جاهز.
  void applyTo(MapController c) {
    final fit = cameraFit;
    if (fit != null) {
      c.fitCamera(fit);
    } else {
      c.move(initialCenter, initialZoom);
    }
  }

  @override
  bool operator ==(Object other) =>
      other is MapViewTarget &&
      other.center == center &&
      other.zoom == zoom &&
      other.bounds == bounds &&
      other.padding == padding &&
      other.maxZoom == maxZoom;

  @override
  int get hashCode => Object.hash(center, zoom, bounds, padding, maxZoom);
}

/// متحكّم أوامريّ. يملكه المستدعي ويتخلّص منه في dispose.
class SahoolMapController {
  SahoolMapController() : map = MapController();

  final MapController map;
  bool _ready = false;
  final _pending = <void Function(MapController)>[];

  bool get isReady => _ready;

  /// الكاميرا الحاليّة؛ null قبل الجاهزيّة.
  MapCamera? get camera => _ready ? map.camera : null;

  /// يستدعيه [SahoolMap] عند onMapReady.
  void attach() {
    _ready = true;
    for (final f in List.of(_pending)) {
      f(map);
    }
    _pending.clear();
  }

  void detach() => _ready = false;

  void _run(void Function(MapController) f) =>
      _ready ? f(map) : _pending.add(f);

  void show(MapViewTarget target) => _run(target.applyTo);

  void fitBounds(
    LatLngBounds b, {
    EdgeInsets padding = const EdgeInsets.all(48),
  }) => show(MapViewTarget.bounds(b, padding: padding));

  void fitGeometry(FieldGeometry g) {
    final t = MapViewTarget.geometry(g);
    if (t != null) show(t);
  }

  void moveTo(LatLng center, {double? zoom}) =>
      _run((c) => c.move(center, zoom ?? c.camera.zoom));

  void zoomBy(double delta) => _run((c) {
    final cam = c.camera;
    c.move(
      cam.center,
      (cam.zoom + delta).clamp(cam.minZoom ?? 1, cam.maxZoom ?? 20),
    );
  });

  void resetRotation() => _run((c) => c.rotate(0));

  void dispose() {
    _pending.clear();
    map.dispose();
  }
}
