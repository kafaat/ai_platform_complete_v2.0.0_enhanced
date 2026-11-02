import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { fmtAge } from './HybridMonitor';

// العطل الذي وُجد هذا لأجله (2026-11-02): الشاشة تسمّي قراءات /telemetry «حيّة» وتعرض
// قراءةً عمرها أيّام كأنّها الآن. صار الخادم يعيد age_sec وstale، والواجهة تُعلِّم القديمة.
const source = readFileSync(join(process.cwd(), 'src/sections/HybridMonitor.tsx'), 'utf8');

describe('HybridMonitor marks stale telemetry', () => {
  it('formats the server-computed age', () => {
    expect(fmtAge(null)).toBe('وقت غير معروف');
    expect(fmtAge(30)).toBe('منذ 1 د');
    expect(fmtAge(20 * 60)).toBe('منذ 20 د');
    expect(fmtAge(5 * 3600)).toBe('منذ 5 س');
    expect(fmtAge(2 * 86400)).toBe('منذ 2 يوم');
  });

  it('shows the stale badge on gauges and on rows, from the server flag', () => {
    expect(source.match(/<StaleBadge p=\{p\} \/>/g)?.length).toBe(2);
    expect(source).toContain('if (!p.stale) return null;');
  });

  it('no longer calls every reading live', () => {
    expect(source).not.toContain('قراءات الحسّاسات الحيّة');
    expect(source).toContain('آخر قراءات الحسّاسات');
  });
});
