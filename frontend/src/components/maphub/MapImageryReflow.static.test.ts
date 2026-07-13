import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

// إصلاح 2026-07-13 (طلب المستخدم): «تختفي الخريطة عند عرض الصور». عند ظهور كتل الصور
// فوق الخريطة داخل نفس العمود يتغيّر صندوقها، لكن محرّك الخريطة يحتفظ بأصل بكسليّ قديم
// ⇒ خريطة رماديّة/فارغة. الإصلاح: مُراقِب أبعاد يُعيد حساب الحجم تلقائيّاً + حصر تمرير
// شريط الصور بـmin-w-0 كي لا يوسّع مسار الشبكة ويزحزح عرض الخريطة.

const read = (rel: string) => readFileSync(join(process.cwd(), rel), 'utf8');

describe('MapHub imagery reflow — الخريطة لا تختفي عند عرض الصور', () => {
  it('Leaflet (HubMap) يُعيد حساب الأبعاد عند التركيب وعبر ResizeObserver', () => {
    const src = read('src/components/maphub/HubMap.tsx');
    expect(src).toContain('function InvalidateOnResize()');
    expect(src).toContain('invalidateSize');
    expect(src).toContain('ResizeObserver');
    // مُركَّب فعليّاً داخل الخريطة (لا تعريف ميّت).
    expect(src).toContain('<InvalidateOnResize />');
    // آمِن في بيئات بلا ResizeObserver (jsdom/SSR).
    expect(src).toContain("typeof ResizeObserver !== 'undefined'");
  });

  it('MapLibre GL (HubMapGL) يستدعي resize() عبر ResizeObserver ويُفكّكه', () => {
    const src = read('src/components/maphub/HubMapGL.tsx');
    expect(src).toContain('new ResizeObserver');
    expect(src).toContain('.resize()');
    expect(src).toContain('resizeObsRef');
    expect(src).toContain('resizeObsRef.current?.disconnect()');
    expect(src).toContain("typeof ResizeObserver !== 'undefined'");
  });

  it('MapHub يحصر تمرير شريط الصور بـmin-w-0 فلا يزحزح عرض الخريطة', () => {
    const src = read('src/sections/MapHub.tsx');
    // العمود المركزيّ (أدوات + خريطة) يحمل min-w-0.
    expect(src).toContain('className="space-y-3 min-w-0"');
    // شريط الصور نفسه أفقيّ التمرير (لا يلتفّ).
    expect(src).toContain('overflow-x-auto');
  });
});
