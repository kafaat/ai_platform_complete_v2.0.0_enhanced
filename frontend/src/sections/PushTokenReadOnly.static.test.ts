import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const src = readFileSync(join(process.cwd(), 'src/sections/NotificationSettingsPage.tsx'), 'utf8');

// continuation-2 #9: رمز الجهاز (Device Token) يُسجّله SDK ويُخزَّن خادم-جانبيّاً —
// لا يُحرّره المستخدم يدويّاً؛ حقله للعرض فقط (readOnly).
describe('push device-token field is read-only', () => {
  it('the push_token TextField is rendered readOnly', () => {
    const idx = src.indexOf('رمز الجهاز (Device Token)');
    expect(idx).toBeGreaterThan(-1);
    const block = src.slice(idx - 200, idx + 300);
    expect(block).toContain('readOnly');
  });

  it('TextField suppresses onChange when readOnly', () => {
    expect(src).toContain('onChange={e => !readOnly && onChange(e.target.value)}');
  });
});
