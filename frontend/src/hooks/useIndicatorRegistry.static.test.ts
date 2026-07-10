import { describe, expect, it } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

// حارس ثابت (source-scan) على عرف WS-B.2 — لا نُشغّل react-query هنا، بل نثبّت أنّ
// القارئ يستهدف نقطة سجلّ المؤشّرات الصحيحة وأنّ HybridIndexPage يستهلك السجلّ
// الحيّ (لا قائمة ثابتة) ويعالج التدهور وحالات التوفّر بصدق. مطابقةً لعرف
// useFieldIrrigationRecommendation.static.test.ts.

const root = path.resolve(__dirname, '..');
const hookFile = path.join(root, 'hooks', 'useIndicatorRegistry.ts');
const pageFile = path.join(root, 'sections', 'HybridIndexPage.tsx');

const hookSrc = fs.readFileSync(hookFile, 'utf8');
const pageSrc = fs.readFileSync(pageFile, 'utf8');

describe('useIndicatorRegistry — reads the WS-B.2 build-time manifest', () => {
  it('sources the generated manifest (no runtime endpoint — p2_6 route ceiling)', () => {
    // مانيفست مُولَّد وقت البناء، لا جلب runtime (لا نقطة منصّة جديدة).
    expect(hookSrc).toContain('indicatorsRegistry.generated');
    expect(hookSrc).toContain('INDICATORS_MANIFEST');
    expect(hookSrc).not.toContain('kongApi');
    expect(hookSrc).not.toContain('/api/v1/indicators/registry');
  });

  it('exports the exact hook name and a typed { data, loading, error } contract', () => {
    expect(hookSrc).toContain('export function useIndicatorRegistry');
    expect(hookSrc).toContain('loading:');
    expect(hookSrc).toContain('error:');
  });

  it('models registry availability/source_class honestly', () => {
    expect(hookSrc).toContain('IndicatorRegistryResponse');
    expect(hookSrc).toContain('registry_version');
    expect(hookSrc).toContain("'active' | 'estimated' | 'unavailable'");
  });
});

describe('HybridIndexPage — consumes the live registry, not a hardcoded catalog', () => {
  it('uses the useIndicatorRegistry hook as the source of the indicator set', () => {
    expect(pageSrc).toContain('useIndicatorRegistry');
    expect(pageSrc).toContain('registry.data.indicators.map');
    // لا مصدر حقيقة ثابت لمجموعة المؤشّرات.
    expect(pageSrc).not.toContain('INDICATOR_CATALOG');
  });

  it('surfaces the registry_version freshness marker', () => {
    expect(pageSrc).toContain('registry_version');
    expect(pageSrc).toContain('نسخة السجلّ');
  });

  it('handles loading and degraded states honestly without a stale hardcoded list', () => {
    expect(pageSrc).toContain('registry.loading');
    expect(pageSrc).toContain('registry.error');
    expect(pageSrc).toContain('تعذّر تحميل سجلّ المؤشّرات');
  });

  it('renders availability honestly: unavailable is marked not-yet-available, estimated is تقديريّ', () => {
    expect(pageSrc).toContain('AvailabilityBadge');
    expect(pageSrc).toContain('غير متاح بعد');
    expect(pageSrc).toContain('تقديريّ');
    expect(pageSrc).toContain("ind.availability === 'unavailable'");
  });
});
