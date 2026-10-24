# Scoped PMTiles / protobuf 6 compatibility fork

This private package preserves the existing offline PMTiles map feature while
LiveKit requires protobuf 6. It is based on the official **pmtiles 1.3.0** archive,
not on pmtiles 2.x (which requires a newer Dart SDK).

- Source archive: <https://pub.dev/api/archives/pmtiles-1.3.0.tar.gz>
- Archive SHA-256: `7e3135c64ec3647e1dd8929fd3c371c8e1c6809b24f1d910d3198a7f41e2068c`
- Upstream release commit: `3797df6e9f49e20a6fda252f564aff393bd4bb7b`
- Repository: <https://github.com/bramp/pmtiles-dart>
- Upstream code license: BSD-2-Clause; the original `LICENSE` is retained.
- Local version: `1.3.0+sahool.1`, with publication disabled.

## Deliberate changes

1. `pubspec.yaml` pins **protobuf 6.0.0** exactly, changes the local version and
   sets `publish_to: none`. The declared Dart minimum is raised to `^3.7.0`,
   matching protobuf 6; the application remains on Dart 3.10. Every other
   upstream dependency constraint remains
   unchanged, including `archive ^3.4.10` and `latlong2 ^0.9.0`.
2. `lib/src/directory.dart` explicitly retains the old protobuf 3.1.0 reader
   limits: **64 MiB** and recursion depth **64**. Protobuf 6 raises these defaults,
   so relying on its defaults would silently broaden the resource limit.

All other copied upstream `lib/` files, LICENSE, README, CHANGELOG and four
retained upstream test files are byte-identical to the verified release archive.
`UPSTREAM_PROVENANCE.json` records their original/local SHA-256 values. The
additional compatibility tests, fixtures, this document, fixture notice and
`analysis_options.yaml` are local packaging additions.

Only `lib/src/directory.dart` imports protobuf. It uses `CodedBufferReader`,
`readUint64`, `readUint32` and `isAtEnd`; it has no generated protobuf messages.
The reviewed protobuf 6.0.0 archive SHA-256 is
`75ec242d22e950bdcc79ee38dd520ce4ee0bc491d7fadc4ea47694604d22bf06`.
The public reader APIs remain available at
<https://pub.dev/documentation/protobuf/6.0.0/protobuf/CodedBufferReader-class.html>.

## Offline verification

From a Flutter/Dart environment with the pinned SDK:

```sh
cd mobile/sahool_app/packages/pmtiles
dart pub get --enforce-lockfile
dart test
```

Dependency installation may require the package registry. The tests themselves
use only local files, memory and temporary files: no HTTP reference server,
external map service, credentials or native device is needed.

The four unchanged upstream tests cover file reads, ranges, tile coordinates and
the loading cache. The added suite preserves rejection of the two original
unclustered vector fixtures, then checks in-memory single-tile variants with only
the clustered header flag changed. It compares the complete decompressed vector
payloads to independently extracted expected bytes. The original raster archive
is read unchanged, with the full returned PNG compared to an independently
extracted fixture. The suite checks gzip metadata and file/memory/batch access. It
also covers malformed/truncated varints and columns, impossible counts, invalid
first offsets, header extent bounds, unsupported/truncated archives and native
integer IDs above 32 and 53 bits.

Upstream `archive_test.dart`, `io_test.dart` and the integration suite are not
copied because their execution includes network/HTTP reference-server paths.
The fixture sources and their separate licenses are recorded in
`test/fixtures/NOTICE.md`; map data is **not** relicensed under BSD-2-Clause.

## Validation boundary

Local validation on 2026-10-24 used the official Dart 3.10.8 SDK, verified against
its published SHA-256. The actual package resolver selected protobuf 6.0.0;
its generated `pubspec.lock` is committed and enforced in CI. All **33 package
tests passed**. Analysis reported no errors and one unchanged upstream warning
(`tile.dart:48`, redundant non-null assertion); the no-fatal-warnings run passed.
All 30 upstream file pairs and six fixtures were hash-verified. The third-party
license now matches its upstream Git blob byte for byte, without an added newline.

The first test run found two incorrect test assumptions about the unclustered
vector fixtures; the tests were corrected as described above, without relaxing
the upstream archive reader. **Application resolution, Flutter tests and APK
build remain pending CI**. Package tests do not prove native application
acceptance. Evidence: `certification/evidence/pmtiles_compatibility_20261024/` at
the repository root.

This is a scoped compatibility change, not general hostile-archive hardening.
Upstream 1.3.0 behavior remains: some sorted/trailing-data checks are assertions,
and values beyond the signed native integer range require separate review.
No test here claims safety for every UInt64 value or every malformed archive.
The old resource limits are retained explicitly without a large-memory test.
