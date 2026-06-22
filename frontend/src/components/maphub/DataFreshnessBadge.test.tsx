// اختبارات DataFreshnessBadge — حالات الشارة الثلاث (FieldView).
// mismatch ⇒ تحذير «عدم تطابق توقيت البيانات»؛ match ⇒ شارة حداثة محايدة؛
// unknown (لا تاريخ طبقة / العرض «latest») ⇒ لا شيء (لا تلفيق).
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import DataFreshnessBadge from './DataFreshnessBadge';

describe('DataFreshnessBadge — حالات توقيت بيانات الطبقة', () => {
  it('تاريخان مختلفان ⇒ تحذير عدم التطابق (role=alert)', () => {
    render(<DataFreshnessBadge layerDate="2026-05-01" displayDate="2026-06-10" indexLabel="NDVI" />);
    expect(screen.getByText(/عدم تطابق توقيت البيانات/)).toBeInTheDocument();
    expect(screen.getByText(/مُشتقّة من مشهد\/مراجعة أقدم/)).toBeInTheDocument();
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  it('تاريخان متطابقان ⇒ شارة حداثة محايدة (role=status، بلا تحذير)', () => {
    render(<DataFreshnessBadge layerDate="2026-06-10" displayDate="2026-06-10" />);
    expect(screen.getByText(/بيانات الطبقة محدّثة لهذا المشهد/)).toBeInTheDocument();
    expect(screen.queryByText(/عدم تطابق/)).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('العرض على «latest» ⇒ لا شيء (unknown — لا تلفيق)', () => {
    const { container } = render(<DataFreshnessBadge layerDate="2026-06-10" displayDate="latest" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('لا تاريخ طبقة ⇒ لا شيء (unknown)', () => {
    const { container } = render(<DataFreshnessBadge layerDate={null} displayDate="2026-06-10" />);
    expect(container).toBeEmptyDOMElement();
  });
});
