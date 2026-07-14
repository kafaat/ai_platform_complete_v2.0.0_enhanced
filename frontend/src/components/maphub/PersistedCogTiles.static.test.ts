import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

// حارس ساكن لإصلاح «الطبقة الورديّة»: حقل محفوظ سابقاً (has_cog) يجب أن يُعرَض من COG
// المحفوظ عبر /tiles لا من تصيير CDSE الحيّ /cdse-tiles. كان MapHub يعرف has_cog لكنّه
// لا يمرّره لمكوّن الخريطة لتبديل الـendpoint. يمنع هذا الحارس رجوع العيب.
const root = process.cwd();
const mapHub = readFileSync(join(root, 'src/sections/MapHub.tsx'), 'utf8');
const hubMap = readFileSync(join(root, 'src/components/maphub/HubMap.tsx'), 'utf8');
const hubMapGL = readFileSync(join(root, 'src/components/maphub/HubMapGL.tsx'), 'utf8');

describe('MapHub uses persisted COG tiles when the selected date has a COG', () => {
  it('MapHub derives selectedDateHasCog and passes preferPersistedCog to both engines', () => {
    expect(mapHub).toContain('selectedDateHasCog');
    expect(mapHub).toContain('preferPersistedCog={selectedDateHasCog}');
    // القرار يعتمد has_cog من التواريخ المتاحة (لا تخمين).
    expect(mapHub).toContain('availableImageryDates.some');
    expect(mapHub).toContain('d.has_cog');
  });

  it('requires explicit indicator COG in indices (keeps TrueColor + unpersisted indices on live path)', () => {
    // نشترط إدراج المؤشّر صراحةً في indices — لا ارتداد «indices فارغة ⇒ نعم». TrueColor
    // لا يُحفَظ كـCOG فلن يُدرَج ⇒ يبقى على /cdse-tiles الحيّ (تبديله ⇒ بلاطة شفّافة).
    expect(mapHub).toContain('_dateHasIndicatorCog');
    expect(mapHub).toContain('String(i).toUpperCase() === _persistNeedle');
    // salinity محفوظ باسم NDSI (تعيين المؤشّر النشط → اسم COG المخزَّن).
    expect(mapHub).toContain("indicatorActive === 'salinity'");
    expect(mapHub).toContain("'NDSI'");
  });

  it('both map engines switch endpoint by preferPersistedCog (/tiles vs /cdse-tiles)', () => {
    // المنطق في الباني المُشترَك (indicatorTileUrl.ts) — نتحقّق منه فيه، ومن أنّ كِلا
    // المحرّكَين يستعملانه.
    const tileUrl = readFileSync(join(root, 'src/components/maphub/indicatorTileUrl.ts'), 'utf8');
    expect(tileUrl).toContain('preferPersistedCog');
    expect(tileUrl).toContain("preferPersistedCog ? 'tiles' : 'cdse-tiles'");
    expect(tileUrl).toContain('if (!preferPersistedCog)');
    for (const [name, src] of [['HubMap', hubMap], ['HubMapGL', hubMapGL]] as const) {
      expect(src, `${name} does not use shared indicatorTileUrl`).toContain('indicatorTileUrl(');
    }
  });
});
