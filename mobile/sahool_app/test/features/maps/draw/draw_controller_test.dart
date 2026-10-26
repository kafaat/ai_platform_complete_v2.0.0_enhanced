import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';
import 'package:sahool_app/features/maps/draw/boundary_validation.dart';
import 'package:sahool_app/features/maps/draw/draw_controller.dart';
import 'package:sahool_app/features/maps/draw/snapping.dart';

const a = LatLng(15.350, 44.200);
const b = LatLng(15.350, 44.210);
const c = LatLng(15.360, 44.210);
const d = LatLng(15.360, 44.200);

void main() {
  group('undo / redo', () {
    test('each tap is one undo step; redo replays; a new edit clears redo', () {
      final ctl = DrawController();
      ctl
        ..tap(a)
        ..tap(b)
        ..tap(c);
      expect(ctl.vertices, [a, b, c]);
      ctl.undo();
      expect(ctl.vertices, [a, b]);
      ctl.undo();
      expect(ctl.vertices, [a]);
      ctl.redo();
      expect(ctl.vertices, [a, b]);
      expect(ctl.canRedo, isTrue);
      ctl.tap(d);
      expect(ctl.canRedo, isFalse);
      expect(ctl.vertices, [a, b, d]);
    });

    test('a whole drag is a single undo step', () {
      final ctl = DrawController()
        ..tap(a)
        ..tap(b)
        ..tap(c);
      ctl.beginEdit();
      for (var i = 1; i <= 10; i++) {
        ctl.updateVertex(2, LatLng(15.36 + i * 0.0001, 44.21));
      }
      ctl.endEdit();
      expect(ctl.vertices[2].latitude, closeTo(15.361, 1e-9));
      ctl.undo();
      expect(ctl.vertices, [a, b, c]);
    });

    test('clear and mode switches are undoable', () {
      final ctl = DrawController()
        ..tap(a)
        ..tap(b)
        ..tap(c);
      ctl.clear();
      expect(ctl.ring, isEmpty);
      ctl.undo();
      expect(ctl.vertices, [a, b, c]);
    });
  });

  group('mode switching regression (49th point / undo eating the circle)', () {
    test(
      'switching from circle to polygon starts empty: next tap is vertex 1',
      () {
        final ctl = DrawController(mode: DrawMode.circle)
          ..tap(a)
          ..setRadius(400);
        expect(ctl.ring, hasLength(96));
        ctl.setMode(DrawMode.polygon);
        ctl.tap(b);
        // قبل الإصلاح: 48 رأساً من الدائرة + الرأس الجديد = 49.
        expect(ctl.ring, [b]);
      },
    );

    test('undo in circle mode never removes a single circle vertex', () {
      final ctl = DrawController(mode: DrawMode.circle)
        ..tap(a)
        ..setRadius(200)
        ..setRadius(300);
      expect(ctl.ring, hasLength(96));
      ctl.undo();
      expect(ctl.ring, hasLength(96), reason: 'يعود نصف القطر السابق كاملاً');
      expect(ctl.radiusM, 200);
      ctl.undo();
      expect(ctl.ring, isEmpty);
      expect(ctl.center, a);
    });

    test('undoing a mode switch restores the previous mode with its shape', () {
      final ctl = DrawController(mode: DrawMode.circle)
        ..tap(a)
        ..setRadius(400)
        ..setMode(DrawMode.polygon)
        ..tap(b);
      ctl.undo();
      ctl.undo();
      expect(ctl.mode, DrawMode.circle);
      expect(ctl.ring, hasLength(96));
    });

    test('circle taps move the centre, they do not add vertices', () {
      final ctl = DrawController(mode: DrawMode.circle)
        ..tap(a)
        ..setRadius(100)
        ..tap(c);
      expect(ctl.center, c);
      expect(ctl.ring, hasLength(96));
    });

    test('point mode holds one location and no boundary', () {
      final ctl = DrawController(mode: DrawMode.point)
        ..tap(a)
        ..tap(b);
      expect(ctl.point, b);
      expect(ctl.ring, isEmpty);
      expect(ctl.geometry, isNull);
    });
  });

  group('rectangle', () {
    test('two taps give four corners; a third starts a new rectangle', () {
      final ctl = DrawController(mode: DrawMode.rectangle)..tap(a);
      expect(ctl.ring, isEmpty);
      ctl.tap(c);
      expect(ctl.ring, [a, b, c, d]);
      ctl.tap(b);
      expect(ctl.ring, isEmpty);
      expect(ctl.cornerA, b);
    });

    test('dragging a corner turns it into an editable polygon', () {
      final ctl = DrawController(mode: DrawMode.rectangle)
        ..tap(a)
        ..tap(c);
      ctl.moveVertex(1, const LatLng(15.349, 44.211));
      expect(ctl.mode, DrawMode.polygon);
      expect(ctl.vertices, hasLength(4));
      expect(ctl.vertices[1], const LatLng(15.349, 44.211));
    });
  });

  group('vertex editing', () {
    test('insert at midpoint and delete', () {
      final ctl = DrawController()
        ..tap(a)
        ..tap(b)
        ..tap(c);
      expect(ctl.midpoints, hasLength(3));
      ctl.insertVertex(0, ctl.midpoints[0]);
      expect(ctl.vertices, hasLength(4));
      expect(ctl.vertices[1], const LatLng(15.350, 44.205));
      ctl.deleteVertex(1);
      expect(ctl.vertices, [a, b, c]);
      ctl.undo();
      expect(ctl.vertices, hasLength(4));
    });

    test('tapping the first vertex closes the polygon without a duplicate', () {
      final ctl = DrawController()
        ..tap(a)
        ..tap(b)
        ..tap(c);
      ctl.tap(const LatLng(15.35001, 44.20001), snapToleranceM: 10);
      expect(ctl.vertices, [a, b, c]);
    });

    test('geometry is a closed [lon,lat] ring', () {
      final ctl = DrawController()
        ..tap(a)
        ..tap(b)
        ..tap(c);
      final g = ctl.geometry!;
      final coords = (g['coordinates'] as List).first as List;
      expect(coords.first, [44.2, 15.35]);
      expect(coords.last, coords.first);
      expect(coords, hasLength(4));
    });
  });

  group('snapping', () {
    final neighbour = ExistingField(
      id: 'n',
      name: 'جار',
      rings: const [
        [
          LatLng(15.350, 44.220),
          LatLng(15.350, 44.230),
          LatLng(15.360, 44.230),
          LatLng(15.360, 44.220),
        ],
      ],
    );

    test(
      'snaps to a neighbour vertex within tolerance, else keeps the tap',
      () {
        final ctl = DrawController()..existingFields = [neighbour];
        ctl.tap(const LatLng(15.35003, 44.22003), snapToleranceM: 8);
        expect(ctl.vertices.single, const LatLng(15.350, 44.220));
        expect(ctl.lastSnap, SnapKind.vertex);
        ctl.tap(const LatLng(15.3, 44.1), snapToleranceM: 8);
        expect(ctl.vertices.last, const LatLng(15.3, 44.1));
      },
    );

    test('snaps to a neighbour edge', () {
      final ctl = DrawController()..existingFields = [neighbour];
      ctl.tap(const LatLng(15.355, 44.22003), snapToleranceM: 8);
      expect(ctl.lastSnap, SnapKind.edge);
      expect(ctl.vertices.single.longitude, closeTo(44.22, 1e-9));
    });

    test('snapping off keeps the raw tap', () {
      final ctl = DrawController()
        ..existingFields = [neighbour]
        ..snapEnabled = false;
      ctl.tap(const LatLng(15.35003, 44.22003), snapToleranceM: 8);
      expect(ctl.vertices.single, const LatLng(15.35003, 44.22003));
    });
  });

  test('pivot payload matches the server contract', () {
    final ctl = DrawController(mode: DrawMode.circle)
      ..tap(const LatLng(15.123456789, 44.987654321))
      ..setRadius(250.456);
    expect(ctl.pivotPayload, {
      'center': {'lon': 44.9876543, 'lat': 15.1234568},
      'radius_m': 250.46,
      'start_angle_deg': 0,
      'end_angle_deg': 360,
      'vertices': 96,
    });
    expect(ctl.boundarySource, 'pivot');
  });

  test('loadRing drops the closing vertex and requests a camera fit', () {
    final ctl = DrawController(mode: DrawMode.circle);
    final before = ctl.fitRequest;
    ctl.loadRing([a, b, c, a], source: 'import_kml');
    expect(ctl.mode, DrawMode.polygon);
    expect(ctl.vertices, [a, b, c]);
    expect(ctl.fitRequest, before + 1);
    expect(ctl.boundarySource, 'import_kml');
  });
}
