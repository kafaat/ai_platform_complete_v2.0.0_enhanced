// حزم الخرائط بلا اتّصال: فتح حقيقيّ لـMBTiles، رفض المفقود/التالف/المتّجه،
// مخزن الحزم (سرد/تفعيل/حذف)، الحزمة تُرسَم فعلاً في SahoolMap، وشاشة الإدارة.
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_map_mbtiles/flutter_map_mbtiles.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mbtiles/mbtiles.dart';
import 'package:sahool_app/features/maps/data/offline_pack_store.dart';
import 'package:sahool_app/features/maps/data/offline_tiles.dart';
import 'package:sahool_app/features/maps/presentation/offline_packs_cubit.dart';
import 'package:sahool_app/features/maps/presentation/offline_packs_screen.dart';
import 'package:sahool_app/features/maps/presentation/widgets/sahool_map.dart';
import 'package:sahool_app/features/maps/presentation/widgets/sahool_map_controller.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'map_test_harness.dart';

String makeMbtiles(Directory dir, String name, {String format = 'png'}) {
  final path = '${dir.path}/$name';
  final db = MbTiles.create(
    mbtilesPath: path,
    metadata: MbTilesMetadata(
      name: name,
      format: format,
      minZoom: 8,
      maxZoom: 14,
      bounds: const MbTilesBounds(
        left: 43.0,
        bottom: 14.0,
        right: 45.0,
        top: 16.0,
      ),
    ),
  );
  db.putTile(z: 8, x: 160, y: 113, bytes: kTransparentPng);
  db.dispose();
  return path;
}

void main() {
  late Directory tmp;
  setUp(() {
    tmp = Directory.systemTemp.createTempSync('sahool_maps_');
    SharedPreferences.setMockInitialValues({});
  });
  tearDown(() {
    if (tmp.existsSync()) tmp.deleteSync(recursive: true);
  });

  group('openOfflinePack', () {
    test(
      'a raster MBTiles pack opens with its zoom range and bounds',
      () async {
        final r = await openOfflinePack(makeMbtiles(tmp, 'sanaa.mbtiles'));
        expect(r.error, isNull);
        final pack = r.pack!;
        expect(pack.format, OfflinePackFormat.mbtiles);
        expect(pack.tileProvider, isA<MbTilesTileProvider>());
        expect(pack.minZoom, 8);
        expect(pack.maxZoom, 14);
        expect(pack.bounds!.west, 43.0);
        await pack.dispose();
      },
    );

    test('vector (pbf) packs are refused with a reason', () async {
      final r = await openOfflinePack(
        makeMbtiles(tmp, 'vec.mbtiles', format: 'pbf'),
      );
      expect(r.pack, isNull);
      expect(r.error, contains('متّجهة'));
    });

    test(
      'missing, corrupt and wrong-extension files fail safe (no throw)',
      () async {
        expect(
          (await openOfflinePack('${tmp.path}/none.mbtiles')).error,
          'ملفّ الحزمة غير موجود',
        );
        final junk = File('${tmp.path}/junk.pmtiles')
          ..writeAsStringSync('nope');
        expect((await openOfflinePack(junk.path)).error, contains('تعذّر فتح'));
        expect(
          (await openOfflinePack('${tmp.path}/x.tif')).error,
          contains('صيغة غير مدعومة'),
        );
      },
    );
  });

  group('OfflinePackStore', () {
    test(
      'lists packs only, activates, forgets a deleted active pack',
      () async {
        final store = OfflinePackStore(roots: () async => [tmp]);
        final a = makeMbtiles(tmp, 'a.mbtiles');
        File('${tmp.path}/b.pmtiles').writeAsStringSync('x');
        File('${tmp.path}/notes.txt').writeAsStringSync('x');
        final packs = await store.list();
        expect(packs.map((p) => p.name).toSet(), {'a.mbtiles', 'b.pmtiles'});
        expect(await store.activePath(), isNull);
        await store.setActive(a);
        expect(await store.activePath(), a);
        await store.delete(packs.firstWhere((p) => p.name == 'a.mbtiles'));
        expect(File(a).existsSync(), isFalse);
        expect(await store.activePath(), isNull);
      },
    );

    test('an active path whose file vanished is not returned', () async {
      final store = OfflinePackStore(roots: () async => [tmp]);
      await store.setActive('${tmp.path}/gone.mbtiles');
      expect(await store.activePath(), isNull);
    });
  });

  testWidgets('SahoolMap actually renders a downloaded MBTiles pack', (
    t,
  ) async {
    final path = await t.runAsync(
      () async => makeMbtiles(tmp, 'aljawf.mbtiles'),
    );
    final ctrl = SahoolMapController();
    addTearDown(ctrl.dispose);
    await t.pumpWidget(
      mapHost(
        SahoolMap(
          controller: ctrl,
          tileProviderFactory: MemoryTileProvider.new,
          offlinePackPath: path,
        ),
      ),
    );
    await t.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 200)),
    );
    await t.pump(const Duration(milliseconds: 100));
    final packLayer = t.widget<TileLayer>(
      find.byKey(ValueKey('offline-pack-$path')),
    );
    expect(packLayer.tileProvider, isA<MbTilesTileProvider>());
    expect(
      t.widget<Text>(find.byKey(const ValueKey('map-source-badge'))).data,
      'خريطة محفوظة على الجهاز',
    );
    expect(
      t.widget<Text>(find.byKey(const ValueKey('map-attribution'))).data,
      contains('aljawf.mbtiles'),
    );
    await t.pumpWidget(const SizedBox());
    await t.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 50)),
    );
  });

  group('offline packs screen', () {
    OfflinePackFile file(String name) => OfflinePackFile(
      path: '/packs/$name',
      name: name,
      format: offlinePackFormatOf(name)!,
      sizeBytes: 3 * 1024 * 1024,
      modified: DateTime(2026, 10, 1),
    );

    testWidgets('lists packs, flags broken ones, activates, confirms delete', (
      t,
    ) async {
      final store = _MemoryStore([file('good.mbtiles'), file('bad.pmtiles')]);
      await t.pumpWidget(
        mapHost(
          OfflinePacksScreen(
            store: store,
            opener: (p) async => p.endsWith('bad.pmtiles')
                ? const OfflinePackOpenResult.failed(
                    'تعذّر فتح الحزمة (ملفّ تالف أو غير مقروء)',
                  )
                : OfflinePackOpenResult.ok(_FakePack()),
          ),
        ),
      );
      await t.pumpAndSettle();
      expect(
        find.textContaining('/packs'),
        findsWidgets,
        reason: 'folder shown',
      );
      expect(find.text('good.mbtiles'), findsOneWidget);
      expect(find.text('غير صالحة'), findsOneWidget);
      expect(
        find.text('تعذّر فتح الحزمة (ملفّ تالف أو غير مقروء)'),
        findsOneWidget,
      );
      expect(find.text('تفعيل'), findsOneWidget, reason: 'only the good pack');
    });

    testWidgets('activate and delete flow', (t) async {
      final store = _MemoryStore([file('good.mbtiles')]);
      await t.pumpWidget(
        mapHost(
          OfflinePacksScreen(
            store: store,
            opener: (_) async => OfflinePackOpenResult.ok(_FakePack()),
          ),
        ),
      );
      await t.pumpAndSettle();
      expect(find.textContaining('تكبير 8–14'), findsOneWidget);
      await t.tap(find.text('تفعيل'));
      await t.pumpAndSettle();
      expect(store.active, '/packs/good.mbtiles');
      expect(find.text('مفعّلة'), findsOneWidget);

      // انتظر زوال الإشعار كي لا يغطّي زرّ الحذف.
      await t.pump(const Duration(seconds: 6));
      await t.pumpAndSettle();
      await t.ensureVisible(find.text('حذف'));
      await t.tap(find.text('حذف'));
      await t.pumpAndSettle();
      expect(find.text('حذف الحزمة؟'), findsOneWidget);
      await t.tap(find.widgetWithText(FilledButton, 'حذف'));
      await t.pumpAndSettle();
      expect(store.files, isEmpty);
      expect(store.active, isNull);
      expect(find.text('لا حزم على الجهاز'), findsOneWidget);
    });

    testWidgets('cancelling the delete keeps the pack', (t) async {
      final store = _MemoryStore([file('good.mbtiles')]);
      await t.pumpWidget(
        mapHost(
          OfflinePacksScreen(
            store: store,
            opener: (_) async => OfflinePackOpenResult.ok(_FakePack()),
          ),
        ),
      );
      await t.pumpAndSettle();
      await t.tap(find.text('حذف'));
      await t.pumpAndSettle();
      await t.tap(find.text('إلغاء'));
      await t.pumpAndSettle();
      expect(store.files, hasLength(1));
    });
  });

  test('cubit: a broken pack cannot be activated', () async {
    final store = _MemoryStore([
      OfflinePackFile(
        path: '/p/x.pmtiles',
        name: 'x.pmtiles',
        format: OfflinePackFormat.pmtiles,
        sizeBytes: 1,
        modified: DateTime(2026),
      ),
    ]);
    final c = OfflinePacksCubit(
      store,
      opener: (_) async => const OfflinePackOpenResult.failed('تالفة'),
    );
    await c.load();
    expect(c.state.packs.single.usable, isFalse);
    await c.activate(c.state.packs.single);
    expect(store.active, isNull);
    await c.close();
  });
}

class _MemoryStore extends OfflinePackStore {
  _MemoryStore(List<OfflinePackFile> files) : files = List.of(files);
  final List<OfflinePackFile> files;
  String? active;

  @override
  Future<List<String>> folders() async => ['/packs'];
  @override
  Future<List<OfflinePackFile>> list() async => List.of(files);
  @override
  Future<String?> activePath() async => active;
  @override
  Future<void> setActive(String? path) async => active = path;
  @override
  Future<void> delete(OfflinePackFile pack) async {
    if (active == pack.path) active = null;
    files.removeWhere((f) => f.path == pack.path);
  }
}

/// حزمة صالحة بلا ملفّ (لشاشة الإدارة).
class _FakePack implements OpenedOfflinePack {
  @override
  String get path => '/packs/good.mbtiles';
  @override
  OfflinePackFormat get format => OfflinePackFormat.mbtiles;
  @override
  int? get minZoom => 8;
  @override
  int? get maxZoom => 14;
  @override
  LatLngBounds? get bounds => null;
  @override
  TileProvider get tileProvider => MemoryTileProvider();
  @override
  Future<void> dispose() async {}
}
