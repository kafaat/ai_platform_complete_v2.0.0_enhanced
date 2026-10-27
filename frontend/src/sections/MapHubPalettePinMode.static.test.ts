// UI-G2 — أمر «دبّوس استكشاف» في لوحة الإجراءات (MapActionPalette) يجب أن يُفعّل
// سطحاً يقبل الدبابيس فعلاً: المحتوى يُقدّم 3D ثمّ المقارنة على الخريطة التفاعليّة،
// وCompareMap يمرّر pinMode={false} وonAddPin no-op. فتفعيل pinMode وحده مع بقاء
// compare/3D يُظهر «وضع الدبابيس» على خريطة لا تقبل دبّوساً. نُقفل هنا أنّ الأمر يخرج
// من 3D والمقارنة ويُطفئ الأوضاع المتنافسة على النقر، كزرّ «دبابيس» في شريط الأدوات.
// (حارس ساكن على نمط MapHubScoutingPinsPersistence — MapHub أثقل من أن يُركَّب هنا.)
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));
const mapHub = readFileSync(join(here, 'MapHub.tsx'), 'utf8');

function paletteHandler(): string {
  const m = mapHub.match(/onPinScouting=\{\(\) => \{([^}]*)\}\}/);
  expect(m, 'onPinScouting handler not found in MapHub.tsx').not.toBeNull();
  return m![1];
}

describe('UI-G2: أمر دبّوس الاستكشاف من اللوحة يُفعّل سطحاً يقبل الدبابيس', () => {
  it('يُفعّل pinMode ويخرج من 3D والمقارنة', () => {
    const body = paletteHandler();
    expect(body).toContain('setPinMode(true)');
    expect(body).toContain("setMode('2d')");
    expect(body).toContain('setCompare(false)');
  });

  it('يُطفئ الأوضاع المتنافسة على نقرات الخريطة (رسم/Pivot/Zones)', () => {
    const body = paletteHandler();
    expect(body).toContain('setDrawTools(false)');
    expect(body).toContain('setPivotDesigner(false)');
    expect(body).toContain('setZoneDesigner(false)');
  });
});
