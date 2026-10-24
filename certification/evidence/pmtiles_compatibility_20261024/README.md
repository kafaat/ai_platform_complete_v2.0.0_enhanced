# PMTiles / LiveKit protobuf compatibility verification

Source base: `c8714330578d33cfbfe9f0d06b0e3bc7494ae1ff`, PR #1263.

`validation.json` identifies all package files and the real package solver lock.
Dart 3.10.8 was downloaded from the official archive and matched its published
SHA-256. The pmtiles 1.3.0 and protobuf 6.0.0 release archives were independently
retrieved and hash-verified. All 30 copied source-file pairs, six fixture hashes,
five original fixture Git blobs and the license Git blob matched.

`dart-tests.txt`: 33 passed, zero failed or skipped. The initial run found two
incorrect fixture expectations (29 passed / 2 failed). pmtiles 1.3.0 rejects
unclustered archives; that behavior remains unchanged. Original fixtures remain
byte-identical. Tests cover rejection plus in-memory single-tile variants with
only the clustered flag changed, comparing complete independently extracted MVT
bytes. Raster reads compare the full original PNG bytes.

`dart-analysis.txt`: no errors, one existing warning in unchanged upstream
`lib/src/tile.dart:48`; `dart analyze --no-fatal-warnings` exits zero.

This is package verification only. Native app dependency resolution, committed
application lock, Flutter analysis/tests, APK and physical-device acceptance
remain separate. No production deployment or main merge is asserted.
