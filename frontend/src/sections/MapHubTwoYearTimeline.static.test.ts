import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const source = readFileSync(join(process.cwd(), 'src/sections/MapHub.tsx'), 'utf8');

describe('MapHub two-year imagery timeline', () => {
  it('adds a visible two-year timeline toggle and panel', () => {
    expect(source).toContain('two-year-imagery-timeline-toggle');
    expect(source).toContain('two-year-imagery-timeline');
    expect(source).toContain('Timeline الصور الجوية · آخر سنتين');
  });

  it('limits the imagery timeline to 730 days from the newest available scene', () => {
    expect(source).toContain('summarizeTwoYearTimeline');
    expect(source).toContain('730 * 24 * 60 * 60 * 1000');
  });

  it('surfaces scene readiness and cloud cover in the timeline UI', () => {
    expect(source).toContain('cloudBandColor');
    expect(source).toContain('جاهز');
    expect(source).toContain('ينتظر COG');
    expect(source).toContain('متوسط غيوم');
  });
});
