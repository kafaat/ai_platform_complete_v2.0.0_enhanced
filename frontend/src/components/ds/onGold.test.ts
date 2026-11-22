import { describe, expect, it } from 'vitest';
import { T, T_DARK } from './tokens';

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// Text on the gold accent stays dark in every theme: the dark palette turns `ink` light
// (#e2e8f0), which on #FFDE00 would fall back to about 1.3:1.
describe('text on gold', () => {
  it('is the same dark ink in the light and dark palettes', () => {
    expect(T.onGold).toBe('#202621');
    expect(T_DARK.onGold).toBe(T.onGold);
  });

  it('meets WCAG AA for normal text on gold', () => {
    expect(contrast(T.onGold, T.gold)).toBeGreaterThanOrEqual(4.5);
  });

  it('would not, with the dark palette ink', () => {
    expect(contrast(T_DARK.ink, T.gold)).toBeLessThan(4.5);
  });
});
