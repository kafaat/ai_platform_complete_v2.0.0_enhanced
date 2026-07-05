import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const source = readFileSync(join(process.cwd(), 'src/sections/MapHub.tsx'), 'utf8');

describe('MapHub two-year imagery timeline', () => {
  it('adds a visible historical imagery timeline toggle and panel', () => {
    expect(source).toContain('two-year-imagery-timeline-toggle');
    expect(source).toContain('two-year-imagery-timeline');
    expect(source).toContain('Timeline الصور الجوية · السلسلة التاريخية');
  });

  it('lets the server bound the timeline range instead of a brittle client-side cutoff', () => {
    // العرض البصري لا يقتصر على «آخر سنتين» بقصٍّ عميلٍ صلب؛ يعرض كل التواريخ الجاهزة
    // التي أرجعها الخادم حتى حدّ الـlimit/السنتين — الخادم يحدّد النطاق الزمني الفعليّ.
    expect(source).toContain('summarizeTwoYearTimeline');
    expect(source).not.toContain('730 * 24 * 60 * 60 * 1000');
    expect(source).toContain('الخادم يحدّد النطاق الزمني الفعلي');
  });

  it('surfaces scene readiness and cloud cover in the timeline UI', () => {
    expect(source).toContain('cloudBandColor');
    expect(source).toContain('جاهز');
    expect(source).toContain('ينتظر COG');
    expect(source).toContain('متوسط غيوم');
  });
});
