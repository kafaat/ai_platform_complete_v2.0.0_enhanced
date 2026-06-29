import fs from 'node:fs';
import path from 'node:path';

describe('map forensic hardening', () => {
  const root = path.resolve(__dirname);
  const gl = fs.readFileSync(path.join(root, 'HubMapGL.tsx'), 'utf8');
  const leaf = fs.readFileSync(path.join(root, 'HubMap.tsx'), 'utf8');

  it('does not update MapLibre raster sources via setTiles', () => {
    const forbidden = '.set' + 'Tiles(';
    expect(gl).not.toContain(forbidden);
    expect(gl).toContain('map.removeSource(SRC_BASEMAP)');
    expect(gl).toContain('map.addSource(SRC_BASEMAP');
  });

  it('passes selected imagery date into raster tile URLs instead of hard-coding latest', () => {
    expect(gl).toContain("date: imageryDate || 'latest'");
    expect(leaf).toContain("date: imageryDate || 'latest'");
    expect(gl).not.toContain("date: 'latest' });");
    expect(leaf).not.toContain("date: 'latest' });");
  });
});
