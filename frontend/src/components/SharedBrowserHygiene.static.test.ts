import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = process.cwd();
const main = readFileSync(join(root, 'src/main.tsx'), 'utf8');
const addField = readFileSync(join(root, 'src/components/AddFieldWithMap.tsx'), 'utf8');

// continuation-1 P1: التفضيلات التشغيليّة المُثبَّتة عالميّاً تُمسَح عند الخروج كي لا
// تعبر بين المستخدمين على متصفّح مُشترَك.
describe('shared-browser hygiene — operational prefs cleared on logout', () => {
  it('main.tsx يمسح sahool_settings عند فقد هويّة المستأجِر', () => {
    const idx = main.indexOf('if (!state.tenantId)');
    expect(idx).toBeGreaterThan(-1);
    const block = main.slice(idx, idx + 400);
    expect(block).toContain("localStorage.removeItem('sahool_settings')");
  });
});

// continuation-1 P1: تحويل MultiPolygon متعدّد الأجزاء لا يُسقِط الأجزاء صامتاً.
describe('MultiPolygon import — silent data loss is surfaced', () => {
  it('firstPolygonFeature يُبلِّغ discardedParts والمُستدعي يُظهِر تنبيهاً', () => {
    expect(addField).toContain('discardedParts');
    expect(addField).toContain('discardedParts: g.coordinates.length - 1');
    expect(addField).toContain('if (discardedParts > 0)');
  });
});
