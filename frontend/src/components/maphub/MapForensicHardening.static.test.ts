import fs from 'node:fs';
import path from 'node:path';

describe('map forensic hardening', () => {
  const root = path.resolve(__dirname);
  const gl = fs.readFileSync(path.join(root, 'HubMapGL.tsx'), 'utf8');
  const leaf = fs.readFileSync(path.join(root, 'HubMap.tsx'), 'utf8');

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
    // عقد التاريخ (D): يمرّر imageryDate المختار شرطيّاً ولا يُثبّت 'latest' (يُسقطه حين latest/فارغ).
    expect(gl).toContain("imageryDate && imageryDate !== 'latest'");
    expect(leaf).toContain("imageryDate && imageryDate !== 'latest'");
    expect(gl).not.toContain("date: 'latest' });");
    expect(leaf).not.toContain("date: 'latest' });");
  });

  it('indicator tiles default to live CDSE path (cdse-tiles) + poly clip; persisted COG only when has_cog (MAPHUB-CDSE)', () => {
    // إصلاح «الطبقة الورديّة»: الافتراضيّ الحيّ cdse-tiles (يحتاج قصّ poly)، ويُبدَّل إلى /tiles
    // المحفوظ فقط حين preferPersistedCog (التاريخ has_cog ⇒ COG مؤكَّد ⇒ لا 404 لحقل بلا معالجة).
    expect(gl).toContain("preferPersistedCog ? 'tiles' : 'cdse-tiles'");
    expect(leaf).toContain("preferPersistedCog ? 'tiles' : 'cdse-tiles'");
    // القصّ (poly) يبقى لمسار CDSE الحيّ فقط — المحفوظ مقصوص مسبقاً.
    expect(gl).toContain('if (!preferPersistedCog)');
    expect(leaf).toContain('if (!preferPersistedCog)');
    expect(gl).toContain("params.set('poly'");
    expect(leaf).toContain("params.set('poly'");
  });

  it('<img> tiles carry access_token so the production auth_request gateway accepts them', () => {
    // بلاطات Leaflet/MapLibre لا تحمل ترويسة Authorization؛ بوّابة الإنتاج تتطلّب JWT.
    // نمرّره كـaccess_token query ليُتحقَّق منه (لا إعفاء أمنيّ). غيابه ⇒ 401 في الإنتاج.
    expect(gl).toContain("params.set('access_token'");
    expect(leaf).toContain("params.set('access_token'");
  });
});
