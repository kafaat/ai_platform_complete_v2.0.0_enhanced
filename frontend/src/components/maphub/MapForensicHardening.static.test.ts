import fs from 'node:fs';
import path from 'node:path';

describe('map forensic hardening', () => {
  const root = path.resolve(__dirname);
  const gl = fs.readFileSync(path.join(root, 'HubMapGL.tsx'), 'utf8');
  const leaf = fs.readFileSync(path.join(root, 'HubMap.tsx'), 'utf8');
  // منطق باني رابط البلاطة استُخرِج إلى وحدة مُشترَكة قابلة للاختبار — نتحقّق من العقود
  // فيها، ومن أنّ كِلا المحرّكَين (HubMap/HubMapGL) يستعملانها فينطبق العقد عليهما.
  const tileUrl = fs.readFileSync(path.join(root, 'indicatorTileUrl.ts'), 'utf8');

  it('does not update MapLibre raster sources via setTiles', () => {
    // الأساس يُحدَّث بإزالة المصدر ثمّ إعادة إضافته (لا setTiles): الإزالة عبر حلقة
    // تشمل SRC_BASEMAP، ثمّ addSource(SRC_BASEMAP) يُعيد إنشاءه.
    const forbidden = '.set' + 'Tiles(';
    expect(gl).not.toContain(forbidden);
    expect(gl).toContain('map.removeSource(sourceId)');
    expect(gl).toContain('SRC_BASEMAP]');
    expect(gl).toContain('map.addSource(SRC_BASEMAP');
  });

  it('passes selected imagery date into raster tile URLs instead of hard-coding latest', () => {
    // عقد التاريخ (D): الباني المُشترَك يمرّر imageryDate شرطيّاً ولا يُثبّت 'latest'.
    expect(tileUrl).toContain("imageryDate && imageryDate !== 'latest'");
    expect(tileUrl).not.toContain("date: 'latest' });");
    // كِلا المحرّكَين يستعملان الباني المُشترَك فينطبق العقد عليهما.
    expect(gl).toContain('indicatorTileUrl(');
    expect(leaf).toContain('indicatorTileUrl(');
  });

  it('indicator tiles default to live CDSE path (cdse-tiles) + poly clip; persisted COG only when has_cog (MAPHUB-CDSE)', () => {
    // إصلاح «الطبقة الورديّة»: الافتراضيّ الحيّ cdse-tiles (يحتاج قصّ poly)، ويُبدَّل إلى /tiles
    // المحفوظ فقط حين preferPersistedCog — في الباني المُشترَك.
    expect(tileUrl).toContain("preferPersistedCog ? 'tiles' : 'cdse-tiles'");
    expect(tileUrl).toContain('if (!preferPersistedCog)');
    expect(tileUrl).toContain("params.set('poly'");
  });

  it('<img> tiles carry access_token so the production auth_request gateway accepts them', () => {
    // بلاطات Leaflet/MapLibre لا تحمل ترويسة Authorization؛ بوّابة الإنتاج تتطلّب JWT.
    // نمرّره كـaccess_token query (في التطوير) ليُتحقَّق منه — في الباني المُشترَك.
    expect(tileUrl).toContain("params.set('access_token'");
  });
});
