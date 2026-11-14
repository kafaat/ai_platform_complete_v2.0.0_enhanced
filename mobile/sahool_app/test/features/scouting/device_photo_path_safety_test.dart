import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/features/scouting/data/device_sources.dart';

void main() {
  group('scouting image identifier rejects path escaping', () {
    test('accepts generated UUID-like identifiers', () {
      expect(DeviceLocalPhotoStore.isValidPinId(
        '019a3350-1983-719d-91e4-111111111111'), isTrue);
    });

    test('rejects traversal, separators and arbitrary unicode', () {
      for (final id in <String>[
        '../other', '..', '/tmp/file', r'..\\other', 'a/b', 'leaf صورة',
        '', List.filled(101, 'A').join(),
      ]) {
        expect(DeviceLocalPhotoStore.isValidPinId(id), isFalse,
          reason: 'Unsafe image identifier: $id');
      }
    });

    test('permits only the media key alphabet', () {
      expect(DeviceLocalPhotoStore.isValidPinId('pin_A-01'), isTrue);
      expect(DeviceLocalPhotoStore.isValidPinId('pin:01'), isFalse);
    });
  });
}
