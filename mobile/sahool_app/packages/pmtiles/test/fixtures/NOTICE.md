# Pinned upstream PMTiles fixtures

These files originate from the pmtiles-dart 1.3.0 release commit
`3797df6e9f49e20a6fda252f564aff393bd4bb7b`, under
`packages/pmtiles_tests/samples/`:

<https://github.com/bramp/pmtiles-dart/tree/3797df6e9f49e20a6fda252f564aff393bd4bb7b/packages/pmtiles_tests/samples>

`test_fixture_1.pmtiles`, `test_fixture_2.pmtiles`, `invalid.pmtiles` and
`invalid_v4.pmtiles` retain their original names and bytes. The upstream samples
README identifies these as the Protomaps PMTiles JavaScript test fixtures:
<https://github.com/protomaps/PMTiles/tree/main/js/test/data>.

`stamen_toner_z3.pmtiles` is a filename-only rename of the unchanged upstream
`stamen_toner(raster)CC-BY+ODbL_z3.pmtiles`. The upstream samples README identifies
it as a PMTiles v3 specification sample:
<https://github.com/protomaps/PMTiles/tree/main/spec/v3>.

Map tiles by **Stamen Design**, licensed under **CC BY 3.0**. Map data by
**OpenStreetMap contributors**, with the upstream fixture explicitly labelled
**ODbL**. This map data is not covered by the package's BSD-2-Clause code license.

- <https://stamen.com/>
- <https://creativecommons.org/licenses/by/3.0/>
- <https://www.openstreetmap.org/copyright>
- <https://opendatacommons.org/licenses/odbl/1-0/>

`stamen_toner_z0_0_0.png` is the unmodified z=0/x=0/y=0 tile payload extracted
from that exact raster archive, retained as an independent expected-byte
fixture; the same attribution applies. No styling, image or map-data alteration
was made. The extraction used a separate Python PMTiles-header/varint reader,
not the Dart package under test.

`PROTOMAPS_LICENSE` retains the upstream project notice (Git blob
`ec3d69a55220793cb4b2074ebe202df25f9cb417`), including its explicit distinction
between code, specification and sample-tileset licensing.

`UPSTREAM_PROVENANCE.json` records the source commit, original path, Git blob
identity and local SHA-256 for each archive, and the PNG's extraction identity.
