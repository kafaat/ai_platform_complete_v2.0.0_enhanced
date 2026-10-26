// SAHOOL — features/maps/presentation/widgets/sahool_map.dart
// الخريطة المشتركة لكلّ شاشات التطبيق (flutter_map 7). تُبنى فوقها طبقات الحقول
// والمؤشّرات والكشّافة والرسم، وتستعملها حزم الرسم (W2-08) والاستيراد (W2-09).
//
// ما تضيفه على الودجت القديم (lib/widgets/offline_field_map.dart):
//   • منتقي خريطة الأساس (سجلّ الويب: أقمار/شوارع/مفاتيح اختياريّة) + تظليل
//     التضاريس من خدمة الراستر حين يقول الخادم إنّه مُهيّأ.
//   • نسبة المصادر ظاهرة دائماً.
//   • أدوات بمواضع اتّجاهيّة (PositionedDirectional): تكبير/تصغير، بوصلة تعيد
//     الشمال، «موقعي» بدائرة الدقّة، ومنتقي الطبقات. أهداف لمس ≥ 48dp.
//   • التدوير معطّل افتراضيّاً (إيماءة بإصبعين أثناء الرسم كانت تميل الخريطة
//     بلا رجعة)؛ عند تفعيله تظهر البوصلة دائماً.
//   • الكاميرا تتبع الحالة: [view] يُطبَّق كلّما تغيّر، و[controller] للأوامر.
//   • حزمة بلا اتّصال ([offlinePackPath]) تُفتح وتُرسَم فعلاً فوق الشبكة
//     (PMTiles/MBTiles)، مع شارة مصدر صادقة وتراجع آمن إلى الشبكة.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/state_views.dart';

import '../../data/basemaps.dart';
import '../../data/device_location.dart';
import '../../data/maps_api.dart';
import '../../data/offline_tiles.dart';
import 'map_attribution.dart';
import 'sahool_map_controller.dart';

/// اسم الحزمة لترويسة User-Agent في طلبات البلاطات (سياسة OSM/CARTO).
const kTileUserAgentPackage = 'ye.sahool.app';

class SahoolMap extends StatefulWidget {
  const SahoolMap({
    super.key,
    this.controller,
    this.view,
    this.layers = const [],
    this.overlays = const [],
    this.initialBasemapId,
    this.onBasemapChanged,
    this.showBasemapSwitcher = true,
    this.allowRotation = false,
    this.showZoomButtons = true,
    this.showLocateButton = true,
    this.locate = locateDevice,
    this.onTap,
    this.offlinePackPath,
    this.extraAttributions = const [],
    this.mapsApi,
    this.tileProviderFactory,
  });

  /// متحكّم الكاميرا (يملكه المستدعي)؛ null ⇒ داخليّ.
  final SahoolMapController? controller;

  /// هدف العرض؛ تغيّره يحرّك الكاميرا. null ⇒ حدود اليمن.
  final MapViewTarget? view;

  /// طبقات flutter_map فوق الأساس (حقول، مؤشّرات، دبابيس، رسم).
  final List<Widget> layers;

  /// ودجات فوق الخريطة (Stack) — أسطورة، شرائح… يضعها المستدعي بمواضع اتّجاهيّة.
  final List<Widget> overlays;

  final String? initialBasemapId;
  final ValueChanged<Basemap>? onBasemapChanged;
  final bool showBasemapSwitcher;
  final bool allowRotation;
  final bool showZoomButtons;
  final bool showLocateButton;
  final LocateFn locate;
  final void Function(LatLng point)? onTap;

  /// مسار حزمة ‎.pmtiles/‎.mbtiles على الجهاز (نظام الملفّات لا assets).
  final String? offlinePackPath;

  /// نسب طبقات إضافيّة (مثل بيانات Sentinel لطبقة المؤشّر).
  final List<String> extraAttributions;

  /// لطبقة التضاريس (التوفّر + ترويسة المصادقة)؛ null ⇒ [MapsApi.instance].
  final MapsApi? mapsApi;

  /// مزوّد بلاطات الأساس الشبكيّة (اختبارات/تخزين مؤقّت)؛ null ⇒ NetworkTileProvider.
  final TileProvider Function()? tileProviderFactory;

  @override
  State<SahoolMap> createState() => SahoolMapState();
}

class SahoolMapState extends State<SahoolMap> {
  late SahoolMapController _ctrl;
  bool _ownsController = false;
  late Basemap _basemap;

  OpenedOfflinePack? _pack;
  String? _packError;
  int _packGeneration = 0;

  bool _terrainOn = false;
  bool _terrainBusy = false;

  // مزوّدو البلاطات يُحفظون عبر عمليّات البناء: مزوّد جديد في كلّ بناء يسرّب عميل
  // HTTP (TileLayer لا يتخلّص إلّا من مزوّده الأخير). يُصفَّر حين يتغيّر مفتاح
  // الطبقة فيتخلّص TileLayer القديم منه.
  TileProvider? _baseProvider;
  TileProvider? _terrainProvider;

  double _rotation = 0;
  LocationFix? _fix;
  bool _locating = false;
  StreamSubscription<MapEvent>? _events;

  SahoolMapController get controller => _ctrl;
  Basemap get basemap => _basemap;
  OpenedOfflinePack? get offlinePack => _pack;

  MapsApi get _api => widget.mapsApi ?? MapsApi.instance;

  @override
  void initState() {
    super.initState();
    _ownsController = widget.controller == null;
    _ctrl = widget.controller ?? SahoolMapController();
    _basemap = Basemaps.byId(widget.initialBasemapId);
    _openPack(widget.offlinePackPath);
  }

  @override
  void didUpdateWidget(SahoolMap oldWidget) {
    super.didUpdateWidget(oldWidget);
    final old = oldWidget;
    if (widget.controller != old.controller) {
      _events?.cancel();
      _events = null;
      if (_ownsController) _ctrl.dispose();
      _ownsController = widget.controller == null;
      _ctrl = widget.controller ?? SahoolMapController();
    }
    // الكاميرا تتبع الحالة: هدف جديد ⇒ حرّك.
    final v = widget.view;
    if (v != null && v != old.view) _ctrl.show(v);
    if (widget.offlinePackPath != old.offlinePackPath) {
      _openPack(widget.offlinePackPath);
    }
  }

  Future<void> _openPack(String? path) async {
    final gen = ++_packGeneration;
    final old = _pack;
    if (path == null) {
      if (old != null || _packError != null) {
        setStateIfMounted(() {
          _pack = null;
          _packError = null;
        });
      }
      await old?.dispose();
      return;
    }
    final result = await openOfflinePack(path);
    if (!mounted || gen != _packGeneration) {
      await result.pack?.dispose(); // طلب أحدث سبقه أو أُزيلت الشاشة
      return;
    }
    setState(() {
      _pack = result.pack;
      _packError = result.error;
    });
    await old?.dispose();
  }

  void setStateIfMounted(VoidCallback f) {
    if (mounted) setState(f);
  }

  void _onMapReady() {
    // flutter_map يطبّق initialCameraFit في استدعاء ما-بعد-الإطار نفسه الذي يلي
    // onMapReady، فيمحو أيّ أمر نُفّذ هنا. نؤجّل تنفيذ الأوامر المصفوفة إطاراً.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _ctrl.attach();
    });
    WidgetsBinding.instance.scheduleFrame();
    _events = _ctrl.map.mapEventStream.listen((e) {
      final r = e.camera.rotation;
      if (r != _rotation && mounted) setState(() => _rotation = r);
    });
  }

  @override
  void dispose() {
    _events?.cancel();
    _ctrl.detach();
    if (_ownsController) _ctrl.dispose();
    _packGeneration++;
    _pack?.dispose();
    super.dispose();
  }

  // ── الإجراءات ────────────────────────────────────────────────────────

  void selectBasemap(Basemap b) {
    if (b.id == _basemap.id) return;
    setState(() {
      _basemap = b;
      _baseProvider = null;
    });
    widget.onBasemapChanged?.call(b);
  }

  Future<void> setTerrain(bool on) async {
    if (!on) {
      setState(() {
        _terrainOn = false;
        _terrainProvider = null;
      });
      return;
    }
    if (_terrainBusy) return;
    setState(() => _terrainBusy = true);
    try {
      final t = await _api.terrainTileJson();
      if (!mounted) return;
      if (!t.available) {
        showSnack(
          context,
          t.userMessage ?? 'التضاريس غير مُهيّأة على الخادم بعد',
          error: true,
        );
        return;
      }
      final headers = await _api.tileHeaders();
      if (!mounted) return;
      setState(() {
        _terrainProvider = NetworkTileProvider(
          headers: headers,
          silenceExceptions: true,
        );
        _terrainOn = true;
      });
    } catch (e) {
      if (mounted) showSnack(context, apiErrorMessage(e), error: true);
    } finally {
      if (mounted) setState(() => _terrainBusy = false);
    }
  }

  Future<void> locateMe() async {
    if (_locating) return;
    setState(() => _locating = true);
    try {
      final fix = await widget.locate();
      if (!mounted) return;
      setState(() => _fix = fix);
      final z = _ctrl.camera?.zoom ?? kSinglePointZoom;
      _ctrl.moveTo(
        fix.point,
        zoom: z < kSinglePointZoom ? kSinglePointZoom : z,
      );
    } on LocationUnavailable catch (e) {
      if (mounted) showSnack(context, e.messageAr, error: true);
    } catch (_) {
      if (mounted) showSnack(context, 'تعذّر تحديد الموقع', error: true);
    } finally {
      if (mounted) setState(() => _locating = false);
    }
  }

  Future<void> _openLayersSheet() async {
    await showModalBottomSheet<void>(
      context: context,
      useSafeArea: true,
      showDragHandle: true,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setSheet) => ListView(
          shrinkWrap: true,
          padding: const EdgeInsetsDirectional.only(bottom: SahoolSpacing.lg),
          children: [
            Padding(
              padding: const EdgeInsetsDirectional.symmetric(
                horizontal: SahoolSpacing.lg,
                vertical: SahoolSpacing.sm,
              ),
              child: Text(
                'خريطة الأساس',
                style: Theme.of(ctx).textTheme.titleMedium,
              ),
            ),
            for (final b in Basemaps.available)
              ListTile(
                key: ValueKey('basemap-${b.id}'),
                minTileHeight: SahoolSizes.minTouchTarget,
                leading: Icon(
                  b.id == _basemap.id
                      ? Icons.radio_button_checked
                      : Icons.radio_button_unchecked,
                ),
                title: Text(b.labelAr),
                subtitle: Text(b.attribution, textDirection: TextDirection.ltr),
                onTap: () {
                  selectBasemap(b);
                  Navigator.of(ctx).pop();
                },
              ),
            const Divider(),
            SwitchListTile(
              key: const ValueKey('terrain-toggle'),
              title: const Text('تظليل التضاريس'),
              subtitle: Text(
                _terrainBusy
                    ? 'جارٍ التحقّق من توفّر التضاريس…'
                    : 'يظهر فقط حين يكون نموذج الارتفاع مُهيّأً على الخادم',
              ),
              value: _terrainOn,
              onChanged: _terrainBusy
                  ? null
                  : (v) async {
                      await setTerrain(v);
                      setSheet(() {});
                    },
            ),
          ],
        ),
      ),
    );
  }

  // ── البناء ───────────────────────────────────────────────────────────

  List<String> get _attributions => [
    _basemap.attribution,
    if (_pack != null) 'خريطة محفوظة: ${_pack!.path.split('/').last}',
    if (_terrainOn) 'Terrain: SAHOOL raster-service (DEM)',
    ...widget.extraAttributions,
  ];

  Widget _baseLayer(BuildContext context) => TileLayer(
    key: ValueKey('basemap-layer-${_basemap.id}'),
    urlTemplate: _basemap.resolvedUrl,
    subdomains: _basemap.subdomains,
    retinaMode: _basemap.retina && RetinaMode.isHighDensity(context),
    maxNativeZoom: _basemap.maxZoom,
    userAgentPackageName: kTileUserAgentPackage,
    tileProvider: _baseProvider ??=
        widget.tileProviderFactory?.call() ??
        NetworkTileProvider(silenceExceptions: true),
  );

  Widget? _packLayer() {
    final p = _pack;
    if (p == null) return null;
    return TileLayer(
      key: ValueKey('offline-pack-${p.path}'),
      tileProvider: p.tileProvider,
      tileBounds: p.bounds,
      minNativeZoom: p.minZoom ?? 0,
      maxNativeZoom: p.maxZoom ?? 19,
      userAgentPackageName: kTileUserAgentPackage,
    );
  }

  List<Widget> _locationLayers(BuildContext context) {
    final fix = _fix;
    if (fix == null) return const [];
    final info = context.tokens.info;
    return [
      if (fix.accuracyM != null)
        CircleLayer(
          circles: [
            CircleMarker(
              point: fix.point,
              radius: fix.accuracyM!,
              useRadiusInMeter: true,
              color: info.withValues(alpha: 0.15),
              borderColor: info,
              borderStrokeWidth: 1,
            ),
          ],
        ),
      MarkerLayer(
        markers: [
          Marker(
            point: fix.point,
            width: 24,
            height: 24,
            child: Semantics(
              label: 'موقعي',
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: info,
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: Theme.of(context).colorScheme.surface,
                    width: 3,
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    ];
  }

  @override
  Widget build(BuildContext context) {
    final view = widget.view ?? MapViewTarget.bounds(kYemenBounds);
    final flags = widget.allowRotation
        ? InteractiveFlag.all
        : InteractiveFlag.all & ~InteractiveFlag.rotate;
    final packLayer = _packLayer();
    return Stack(
      children: [
        FlutterMap(
          mapController: _ctrl.map,
          options: MapOptions(
            initialCameraFit: view.cameraFit,
            initialCenter: view.initialCenter,
            initialZoom: view.initialZoom,
            minZoom: 3,
            maxZoom: 20,
            interactionOptions: InteractionOptions(flags: flags),
            onMapReady: _onMapReady,
            onTap: widget.onTap == null ? null : (_, p) => widget.onTap!(p),
          ),
          children: [
            _baseLayer(context),
            if (packLayer != null) packLayer,
            if (_terrainOn && _terrainProvider != null)
              TileLayer(
                key: const ValueKey('terrain-hillshade'),
                urlTemplate: _api.hillshadeTileUrl(),
                minNativeZoom: 8,
                maxNativeZoom: 17,
                userAgentPackageName: kTileUserAgentPackage,
                tileProvider: _terrainProvider,
                tileBuilder: (context, tile, _) =>
                    Opacity(opacity: 0.7, child: tile),
              ),
            ...widget.layers,
            ..._locationLayers(context),
          ],
        ),
        PositionedDirectional(
          top: SahoolSpacing.sm,
          start: SahoolSpacing.sm,
          end: 72, // يترك عمود الأدوات حرّاً
          child: Align(
            alignment: AlignmentDirectional.topStart,
            child: _SourceBadge(offline: _pack != null, packError: _packError),
          ),
        ),
        PositionedDirectional(
          top: SahoolSpacing.sm,
          end: SahoolSpacing.sm,
          child: _controls(),
        ),
        PositionedDirectional(
          bottom: SahoolSpacing.xs,
          start: SahoolSpacing.xs,
          child: MapAttribution(sources: _attributions),
        ),
        ...widget.overlays,
      ],
    );
  }

  Widget _controls() {
    final showCompass = widget.allowRotation || _rotation != 0;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (widget.showBasemapSwitcher)
          MapControlButton(
            key: const ValueKey('map-layers'),
            icon: Icons.layers_outlined,
            tooltip: 'طبقات الخريطة',
            onPressed: _openLayersSheet,
          ),
        if (widget.showZoomButtons) ...[
          MapControlButton(
            key: const ValueKey('map-zoom-in'),
            icon: Icons.add,
            tooltip: 'تكبير',
            onPressed: () => _ctrl.zoomBy(1),
          ),
          MapControlButton(
            key: const ValueKey('map-zoom-out'),
            icon: Icons.remove,
            tooltip: 'تصغير',
            onPressed: () => _ctrl.zoomBy(-1),
          ),
        ],
        if (showCompass)
          MapControlButton(
            key: const ValueKey('map-compass'),
            tooltip: 'إعادة الشمال للأعلى',
            onPressed: _ctrl.resetRotation,
            child: Transform.rotate(
              angle: -_rotation * 3.141592653589793 / 180,
              child: const Icon(Icons.navigation_outlined),
            ),
          ),
        if (widget.showLocateButton)
          MapControlButton(
            key: const ValueKey('map-locate'),
            icon: Icons.my_location,
            tooltip: 'موقعي',
            busy: _locating,
            onPressed: locateMe,
          ),
      ],
    );
  }
}

/// زرّ أداة خريطة: دائريّ على سطح شبه معتم، هدف لمس 48dp، وتلميح إلزاميّ.
class MapControlButton extends StatelessWidget {
  const MapControlButton({
    super.key,
    required this.tooltip,
    required this.onPressed,
    this.icon,
    this.child,
    this.busy = false,
  }) : assert(icon != null || child != null);

  final String tooltip;
  final VoidCallback? onPressed;
  final IconData? icon;
  final Widget? child;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsetsDirectional.only(bottom: SahoolSpacing.sm),
      child: Material(
        color: scheme.surface.withValues(alpha: 0.92),
        shape: const CircleBorder(),
        elevation: 2,
        child: IconButton(
          tooltip: tooltip,
          onPressed: busy ? null : onPressed,
          color: scheme.onSurface,
          constraints: const BoxConstraints(
            minWidth: SahoolSizes.minTouchTarget,
            minHeight: SahoolSizes.minTouchTarget,
          ),
          icon: busy
              ? const SizedBox(
                  width: SahoolSizes.iconSm,
                  height: SahoolSizes.iconSm,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : (child ?? Icon(icon)),
        ),
      ),
    );
  }
}

class _SourceBadge extends StatelessWidget {
  const _SourceBadge({required this.offline, this.packError});
  final bool offline;
  final String? packError;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final t = context.tokens;
    final text = packError != null
        ? 'الخريطة المحفوظة غير متاحة ($packError) — تُعرض خريطة الشبكة'
        : (offline ? 'خريطة محفوظة على الجهاز' : 'خريطة الشبكة');
    return Semantics(
      liveRegion: packError != null,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: scheme.surface.withValues(alpha: 0.88),
          borderRadius: SahoolRadius.smAll,
        ),
        child: Padding(
          padding: const EdgeInsetsDirectional.symmetric(
            horizontal: SahoolSpacing.sm,
            vertical: SahoolSpacing.xs,
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                packError != null
                    ? Icons.warning_amber_rounded
                    : (offline ? Icons.offline_pin_outlined : Icons.public),
                size: SahoolSizes.iconSm,
                color: packError != null ? t.warning : t.muted,
              ),
              const SizedBox(width: SahoolSpacing.xs),
              Flexible(
                child: Text(
                  text,
                  key: const ValueKey('map-source-badge'),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontSize: SahoolType.caption, color: t.ink),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
