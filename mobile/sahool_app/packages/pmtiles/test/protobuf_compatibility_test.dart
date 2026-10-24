@TestOn('vm')
import 'dart:io';
import 'dart:typed_data';

import 'package:pmtiles/pmtiles.dart';
import 'package:pmtiles/src/directory.dart' as pm;
import 'package:protobuf/protobuf.dart';
import 'package:test/test.dart';

File fixture(String name) => File('test/fixtures/$name');

// Independent unsigned base-128 encoder for small deterministic directory cases.
List<int> varint(int value) {
  final bytes = <int>[];
  do {
    final low = value & 0x7f;
    value >>= 7;
    bytes.add(low | (value == 0 ? 0 : 0x80));
  } while (value != 0);
  return bytes;
}

void main() {
  group('protobuf 6 bounded directory compatibility', () {
    test('decodes columns, delta IDs and implicit contiguous offsets', () {
      final directory = pm.Directory.from([2, 0, 1, 1, 1, 3, 4, 1, 0]);
      expect(directory.entries.map((entry) => entry.tileId), [0, 1]);
      expect(directory.find(0)!.length, 3);
      expect(directory.find(1)!.offset, 3);
      expect(directory.find(1)!.length, 4);
      expect(directory.find(2), isNull);
    });

    for (final tileId in [(1 << 32) + 1, (1 << 53) + 1]) {
      test('preserves native UInt64 tile ID $tileId', () {
        final directory = pm.Directory.from([1, ...varint(tileId), 1, 1, 1]);
        expect(directory.entries.single.tileId, tileId);
        expect(directory.find(tileId)!.runLength, 1);
      });
    }

    test('rejects an unterminated count varint', () {
      expect(
        () => pm.Directory.from([0x80]),
        throwsA(isA<InvalidProtocolBufferException>()),
      );
    });

    test('rejects a malformed ten-byte count varint', () {
      expect(
        () => pm.Directory.from(List.filled(10, 0x80)),
        throwsA(isA<InvalidProtocolBufferException>()),
      );
    });

    test('rejects a truncated offset column', () {
      expect(
        () => pm.Directory.from([1, 0, 1, 1]),
        throwsA(isA<InvalidProtocolBufferException>()),
      );
    });

    test('rejects a count larger than the available columns', () {
      expect(
        () => pm.Directory.from([2, 0, 1, 1]),
        throwsA(isA<CorruptArchiveException>()),
      );
      expect(
        () => pm.Directory.from(varint(1 << 32)),
        throwsA(isA<CorruptArchiveException>()),
      );
    });

    test('rejects implicit offset zero for the first entry', () {
      expect(
        () => pm.Directory.from([1, 0, 1, 1, 0]),
        throwsA(isA<CorruptArchiveException>()),
      );
    });

    test('rejects a tile extent outside the supplied header', () {
      final data = ByteData(headerLength)..setUint64(0x40, 1, Endian.little);
      expect(
        () => pm.Directory.from([1, 0, 1, 2, 1], header: Header(data)),
        throwsA(isA<CorruptArchiveException>()),
      );
    });

    test('rejects a leaf extent outside the supplied header', () {
      final data = ByteData(headerLength)..setUint64(0x30, 1, Endian.little);
      expect(
        () => pm.Directory.from([1, 0, 0, 2, 1], header: Header(data)),
        throwsA(isA<CorruptArchiveException>()),
      );
    });
  });

  group('pinned upstream archives, without a network service', () {
    // Independently extracted with Python's gzip reader from the pinned
    // archives' tile-data section; these are complete uncompressed MVT bytes.
    const expectedVectorHex = {
      'test_fixture_1.pmtiles':
          '1a2f78020a15746573745f666978747572655f31706d74696c657328802012111803220d099620e81f1a0018150000170f',
      'test_fixture_2.pmtiles':
          '1a2d78020a15746573745f666978747572655f32706d74696c6573288020120f1803220b098020e81f12161815000f',
    };
    for (final name in ['test_fixture_1.pmtiles', 'test_fixture_2.pmtiles']) {
      test('preserves upstream rejection of unclustered $name', () async {
        final bytes = await fixture(name).readAsBytes();
        expect(bytes[0x60], 0);
        await expectLater(
          PmTilesArchive.fromBytes(bytes),
          throwsA(isA<UnsupportedError>()),
        );
      });

      test(
        'reads gzip metadata and vector tile from clustered $name variant',
        () async {
          final original = await fixture(name).readAsBytes();
          final bytes = Uint8List.fromList(original);
          // These single-tile upstream samples carry clustered=0, which 1.3.0
          // deliberately rejects. Change only that flag in memory; retain the
          // original fixtures and every compressed payload byte unchanged.
          expect(bytes[0x60], 0);
          bytes[0x60] = 1;
          expect(bytes.sublist(0, 0x60), original.sublist(0, 0x60));
          expect(bytes.sublist(0x61), original.sublist(0x61));
          final archive = await PmTilesArchive.fromBytes(bytes);
          try {
            expect(archive.version, 3);
            expect(archive.tileType, TileType.mvt);
            expect(archive.tileCompression, Compression.gzip);
            final metadata = (await archive.metadata) as Map<String, dynamic>;
            expect(metadata['name'], name);
            final tile = await archive.tile(ZXY(0, 0, 0).toTileId());
            final expectedHex = expectedVectorHex[name]!;
            final expected = [
              for (var i = 0; i < expectedHex.length; i += 2)
                int.parse(expectedHex.substring(i, i + 2), radix: 16),
            ];
            expect(tile.bytes(), expected);
            final missing = await archive.tile(ZXY(1, 0, 0).toTileId());
            expect(missing.bytes, throwsA(isA<TileNotFoundException>()));
          } finally {
            await archive.close();
          }
        },
      );
    }

    test(
      'reads the exact upstream raster PNG through file and memory APIs',
      () async {
        final expected = await fixture('stamen_toner_z0_0_0.png').readAsBytes();
        expect(expected.length, 18404);
        expect(expected.take(8), [137, 80, 78, 71, 13, 10, 26, 10]);
        final bytes = await fixture('stamen_toner_z3.pmtiles').readAsBytes();
        for (final memory in [false, true]) {
          final archive =
              memory
                  ? await PmTilesArchive.fromBytes(bytes)
                  : await PmTilesArchive.fromFile(
                    fixture('stamen_toner_z3.pmtiles'),
                  );
          try {
            expect(archive.tileType, TileType.png);
            expect(archive.minZoom, 0);
            expect(archive.maxZoom, 3);
            final tile = await archive.tile(0);
            expect(tile.bytes(), expected);
            final batch = await archive.tiles([0]).toList();
            expect(batch.single.bytes(), expected);
          } finally {
            await archive.close();
          }
        }
      },
    );

    test('rejects the upstream invalid header fixture', () async {
      final bytes = await fixture('invalid.pmtiles').readAsBytes();
      await expectLater(
        PmTilesArchive.fromBytes(bytes),
        throwsA(isA<CorruptArchiveException>()),
      );
    });

    test('rejects the upstream unsupported version fixture', () async {
      final bytes = await fixture('invalid_v4.pmtiles').readAsBytes();
      await expectLater(
        PmTilesArchive.fromBytes(bytes),
        throwsA(isA<UnsupportedError>()),
      );
    });

    test('rejects a truncated archive before reading its directory', () async {
      await expectLater(
        PmTilesArchive.fromBytes([0x50, 0x4d]),
        throwsA(isA<CorruptArchiveException>()),
      );
    });
  });
}
