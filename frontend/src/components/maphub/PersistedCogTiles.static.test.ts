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

  it('both map engines switch endpoint by preferPersistedCog (/tiles vs /cdse-tiles)', () => {
    for (const [name, src] of [['HubMap', hubMap], ['HubMapGL', hubMapGL]] as const) {
      expect(src, `${name} missing preferPersistedCog param`).toContain('preferPersistedCog');
      expect(src, `${name} does not switch segment`).toContain(
        "preferPersistedCog ? 'tiles' : 'cdse-tiles'",
      );
      // القصّ (poly) لمسار CDSE الحيّ فقط — المحفوظ مقصوص مسبقاً.
      expect(src, `${name} does not gate poly on live path`).toContain('if (!preferPersistedCog)');
    }
  });
});
