// اختبارات عناصر النموذج (DS) — الربط الوصوليّ (label↔input)، عرض الخطأ مع
// aria-invalid/role=alert، والتحكّم (onChange يُبلّغ القيمة الجديدة).
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Input, Textarea, Select, Checkbox, Radio } from './forms';

describe('Input', () => {
  it('يربط التسمية بالحقل ويُبلّغ التغيير', () => {
    const onChange = vi.fn();
    render(<Input label="الاسم" value="" onChange={onChange} />);
    const field = screen.getByLabelText('الاسم');
    fireEvent.change(field, { target: { value: 'أحمد' } });
    expect(onChange).toHaveBeenCalledWith('أحمد');
  });

  it('يعرض الخطأ مع aria-invalid وrole=alert', () => {
    render(<Input label="الهاتف" value="" onChange={() => {}} error="مطلوب" />);
    expect(screen.getByRole('alert')).toHaveTextContent('مطلوب');
    expect(screen.getByLabelText('الهاتف')).toHaveAttribute('aria-invalid', 'true');
  });

  it('يعرض التلميح حين لا خطأ', () => {
    render(<Input label="المساحة" value="" onChange={() => {}} hint="بالهكتار" />);
    expect(screen.getByText('بالهكتار')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
  });
});

describe('Textarea', () => {
  it('مُتحكَّم به ويُبلّغ التغيير', () => {
    const onChange = vi.fn();
    render(<Textarea label="ملاحظة" value="x" onChange={onChange} />);
    fireEvent.change(screen.getByLabelText('ملاحظة'), { target: { value: 'xy' } });
    expect(onChange).toHaveBeenCalledWith('xy');
  });
});

describe('Select', () => {
  it('يعرض الخيارات ويُبلّغ الاختيار', () => {
    const onChange = vi.fn();
    render(
      <Select
        label="المحصول"
        value=""
        onChange={onChange}
        placeholder="اختر"
        options={[
          { value: 'wheat', label: 'قمح' },
          { value: 'corn', label: 'ذرة' },
        ]}
      />,
    );
    fireEvent.change(screen.getByLabelText('المحصول'), { target: { value: 'corn' } });
    expect(onChange).toHaveBeenCalledWith('corn');
  });
});

describe('Checkbox', () => {
  it('يبدّل الحالة عبر onChange', () => {
    const onChange = vi.fn();
    render(<Checkbox label="موافق" checked={false} onChange={onChange} />);
    fireEvent.click(screen.getByLabelText('موافق'));
    expect(onChange).toHaveBeenCalledWith(true);
  });
});

describe('Radio', () => {
  it('مجموعة radiogroup تُبلّغ الخيار المختار', () => {
    const onChange = vi.fn();
    render(
      <Radio
        name="rg"
        label="الرّيّ"
        value=""
        onChange={onChange}
        options={[
          { value: 'drip', label: 'تنقيط' },
          { value: 'pivot', label: 'محوريّ' },
        ]}
      />,
    );
    expect(screen.getByRole('radiogroup')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('محوريّ'));
    expect(onChange).toHaveBeenCalledWith('pivot');
  });
});
