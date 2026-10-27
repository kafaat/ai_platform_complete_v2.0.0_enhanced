// شريط Satellite (DateScrubber) — صدق المصغّرة ووقت الالتقاط.
//
// T5: وقت بلا منطقة زمنيّة كان يُمرَّر إلى `new Date` (يُفسَّر بتوقيت المتصفّح) ثمّ يُعرَض
//     موسوماً «UTC» — ساعة مفترضة تُقدَّم كأنّها UTC مقيسة. السياسة الموحّدة (captureTime):
//     ساعة UTC تُعرَض فقط لطابع UTC صريح؛ غير ذلك لا ساعة.
// T6: `onError` كان يُخفي الصورة ويترك تدرّجاً بلون القيمة قد يُقرأ صورةً حقيقيّة.
// T7: المصغّرة قد تكون مؤشّراً ملوّناً لا لوناً حقيقيّاً — تُوسَم بالمنتَج المعروض.
import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import DateScrubber, { type ScrubberPoint } from './DateScrubber';

function renderOne(p: Partial<ScrubberPoint>) {
  const point: ScrubberPoint = { date: '2026-10-20', value: 0.62, cloud: 5, ...p };
  return render(<DateScrubber points={[point]} selected="" onSelect={() => {}} />);
}

describe('DateScrubber — وقت الالتقاط (T5)', () => {
  it('طابع UTC صريح ⇒ ساعة موسومة UTC', () => {
    renderOne({ acquisitionDatetime: '2026-10-20T10:37:00Z' });
    expect(screen.getByText(/10:37 UTC/)).toBeInTheDocument();
  });

  it('طابع بلا منطقة زمنيّة ⇒ لا ادّعاء ساعة UTC', () => {
    const { container } = renderOne({ acquisitionDatetime: '2026-10-20T10:37:00' });
    expect(container.textContent).not.toMatch(/UTC/);
    expect(container.querySelector('button')?.getAttribute('title') ?? '').not.toMatch(/UTC/);
  });
});

describe('DateScrubber — فشل المصغّرة حالة صريحة (T6)', () => {
  it('خطأ تحميل ⇒ «تعذّر العرض» ولا تدرّج لونيّ يشبه صورة', () => {
    renderOne({ thumbUrl: '/thumb.png' });
    fireEvent.error(screen.getByTestId('scrubber-thumb-img'));
    expect(screen.getByText('تعذّر العرض')).toBeInTheDocument();
    expect(screen.queryByTestId('scrubber-thumb-img')).not.toBeInTheDocument();
    expect(screen.getByTestId('scrubber-thumb').getAttribute('style') ?? '').not.toMatch(/gradient/);
  });

  it('بلا رابط ⇒ «لا صورة» لا مساحة ملوّنة صامتة', () => {
    renderOne({ thumbUrl: null });
    expect(screen.getByText('لا صورة')).toBeInTheDocument();
    expect(screen.getByTestId('scrubber-thumb').getAttribute('style') ?? '').not.toMatch(/gradient/);
  });
});

describe('DateScrubber — وسم المنتَج المعروض (T7)', () => {
  it('مؤشّر ملوّن ⇒ اسم المؤشّر على المصغّرة', () => {
    renderOne({ thumbUrl: '/thumb.png', thumbProduct: 'ndmi' });
    expect(screen.getByTestId('scrubber-thumb-product')).toHaveTextContent('NDMI');
  });

  it('truecolor ⇒ «لون حقيقيّ»', () => {
    renderOne({ thumbUrl: '/thumb.png', thumbProduct: 'truecolor' });
    expect(screen.getByTestId('scrubber-thumb-product')).toHaveTextContent('لون حقيقيّ');
  });
});
