// ═══════════════════════════════════════════════════════════════
// دلالات وراثة النغمة (A: مراجعة #857) — العقد المقيس:
//   undefined = يرث نغمة الأصل · الصريح (light/dark) = يفرض نغمته.
// العطل الذي أمسكته المراجعة: FieldCabin كان افتراضيّه tone='light'
// فيُعيد أحفادَ شجرةٍ داكنة إلى الفاتح قسراً عن غير قصد.
// ═══════════════════════════════════════════════════════════════
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { DsThemeProvider, resolveTokens, useT } from './theme';
import { T, T_DARK } from './tokens';
import { FieldCabin } from './cabin';

function Probe({ id }: { id: string }) {
  const t = useT();
  const tone = t === T_DARK ? 'dark' : t === T ? 'light' : 'other';
  return <span data-testid={id}>{tone}</span>;
}

describe('resolveTokens — الصريح يفرض وundefined يرث', () => {
  it('undefined يُرجِع سياق الأصل كما هو', () => {
    expect(resolveTokens(undefined, T_DARK)).toBe(T_DARK);
    expect(resolveTokens(undefined, T)).toBe(T);
  });
  it('القيمة الصريحة تفرض نغمتها بمعزل عن السياق', () => {
    expect(resolveTokens('dark', T)).toBe(T_DARK);
    expect(resolveTokens('light', T_DARK)).toBe(T);
  });
});

describe('DsThemeProvider — التداخل لا يعيد الفاتح عن غير قصد', () => {
  it('مزوّد بلا نغمة داخل شجرة داكنة يبقى داكناً (يرث)', () => {
    render(
      <DsThemeProvider tone="dark">
        <DsThemeProvider>
          <Probe id="nested-inherit" />
        </DsThemeProvider>
      </DsThemeProvider>,
    );
    expect(screen.getByTestId('nested-inherit').textContent).toBe('dark');
  });
  it('مزوّد صريح الفاتح داخل شجرة داكنة يفرض الفاتح', () => {
    render(
      <DsThemeProvider tone="dark">
        <DsThemeProvider tone="light">
          <Probe id="nested-force-light" />
        </DsThemeProvider>
      </DsThemeProvider>,
    );
    expect(screen.getByTestId('nested-force-light').textContent).toBe('light');
  });
});

describe('FieldCabin — النغمة تُورَّث للأحفاد ولا تُفرَض فاتحةً افتراضاً', () => {
  it('كابينة بلا tone داخل أصل داكن لا تُعيد أحفادها إلى الفاتح', () => {
    render(
      <DsThemeProvider tone="dark">
        <FieldCabin eyebrow="e" title="t">
          <Probe id="cabin-inherit" />
        </FieldCabin>
      </DsThemeProvider>,
    );
    expect(screen.getByTestId('cabin-inherit').textContent).toBe('dark');
  });
  it('tone="dark" على الكابينة يصل الأحفادَ بلا tone صريح (يرثون الداكن)', () => {
    render(
      <FieldCabin eyebrow="e" title="t" tone="dark">
        <Probe id="cabin-dark-child" />
      </FieldCabin>,
    );
    expect(screen.getByTestId('cabin-dark-child').textContent).toBe('dark');
  });
  it('كابينة بلا tone وبلا أصل داكن تبقى فاتحة (السلوك القائم محفوظ)', () => {
    render(
      <FieldCabin eyebrow="e" title="t">
        <Probe id="cabin-default" />
      </FieldCabin>,
    );
    expect(screen.getByTestId('cabin-default').textContent).toBe('light');
  });
});

describe('FieldCabin subtitle — من سلطة الرموز لا من hex مبثوث', () => {
  it('السطر الوصفيّ يقرأ t.subtitle في النغمتين', () => {
    render(
      <FieldCabin eyebrow="e" title="t" subtitle="SUB-L">
        <span />
      </FieldCabin>,
    );
    expect(screen.getByText('SUB-L')).toHaveStyle({ color: T.subtitle });
    render(
      <FieldCabin eyebrow="e" title="t" subtitle="SUB-D" tone="dark">
        <span />
      </FieldCabin>,
    );
    expect(screen.getByText('SUB-D')).toHaveStyle({ color: T_DARK.subtitle });
  });

  it('تغيير T_DARK.subtitle ينعكس على الكابينة (لا قيمة مثبَّتة داخل المكوّن)', () => {
    const original = T_DARK.subtitle;
    try {
      (T_DARK as { subtitle: string }).subtitle = 'rgb(1, 2, 3)';
      render(
        <FieldCabin eyebrow="e" title="t" subtitle="SUB-X" tone="dark">
          <span />
        </FieldCabin>,
      );
      expect(screen.getByText('SUB-X')).toHaveStyle({ color: 'rgb(1, 2, 3)' });
    } finally {
      (T_DARK as { subtitle: string }).subtitle = original;
    }
  });
});
