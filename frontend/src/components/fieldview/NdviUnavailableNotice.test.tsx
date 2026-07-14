// اختبارات NdviUnavailableNotice — العقد التشخيصيّ 424 (حالة فارغة هادئة).
// (1) ndviUnavailableFromError: يستخرج التفصيل المُصنَّف من 424، يتجاهل غير-424،
//     ويعامِل 424 القديم (تفصيل نصّيّ) كـ«لا صور مُعالَجة».
// (2) المكوّن: يُصيّر رسالة عربيّة لكلّ code (role=status)، ويُظهر زرّ المعالجة
//     فقط للحالات الحتميّة (retryable:false + cta + معالِج) لا للأعطال العابرة/التفويض.
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import NdviUnavailableNotice, { ndviUnavailableFromError } from './NdviUnavailableNotice';

function axios424(detail: unknown) {
  return { response: { status: 424, data: { detail } } };
}

describe('ndviUnavailableFromError — استخراج تفصيل 424', () => {
  it('424 بتفصيل مُصنَّف ⇒ يعيد الكائن كما هو', () => {
    const info = ndviUnavailableFromError(
      axios424({ code: 'NO_PROCESSED_IMAGERY', message: 'x', action: 'RUN_IMAGERY_BACKFILL', retryable: false }),
    );
    expect(info).toEqual({
      code: 'NO_PROCESSED_IMAGERY',
      message: 'x',
      action: 'RUN_IMAGERY_BACKFILL',
      retryable: false,
    });
  });

  it('424 بتفصيل نصّيّ قديم ⇒ يسقط إلى NO_PROCESSED_IMAGERY (retryable:false)', () => {
    const info = ndviUnavailableFromError(axios424('no imagery'));
    expect(info).toEqual({ code: 'NO_PROCESSED_IMAGERY', retryable: false });
  });

  it('غير 424 (500) ⇒ null', () => {
    expect(ndviUnavailableFromError({ response: { status: 500, data: {} } })).toBeNull();
  });

  it('خطأ بلا response (شبكة) ⇒ null', () => {
    expect(ndviUnavailableFromError(new Error('network'))).toBeNull();
  });

  it('null/undefined ⇒ null', () => {
    expect(ndviUnavailableFromError(null)).toBeNull();
    expect(ndviUnavailableFromError(undefined)).toBeNull();
  });
});

describe('NdviUnavailableNotice — تصيير الحالة الفارغة', () => {
  it('NO_PROCESSED_IMAGERY (حتميّ) ⇒ رسالة + زرّ معالجة (role=status)', () => {
    const onProcess = vi.fn();
    render(
      <NdviUnavailableNotice
        info={{ code: 'NO_PROCESSED_IMAGERY', retryable: false }}
        onProcess={onProcess}
      />,
    );
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.getByText(/لا توجد صور أقمار صناعيّة مُعالَجة/)).toBeInTheDocument();
    const btn = screen.getByRole('button', { name: /معالجة الصور/ });
    fireEvent.click(btn);
    expect(onProcess).toHaveBeenCalledTimes(1);
  });

  it('عطل عابر (RASTER_DEPENDENCY_UNAVAILABLE) ⇒ رسالة بلا زرّ معالجة', () => {
    render(
      <NdviUnavailableNotice
        info={{ code: 'RASTER_DEPENDENCY_UNAVAILABLE', retryable: true }}
        onProcess={() => {}}
      />,
    );
    expect(screen.getByText(/خدمة معالجة الصور غير متاحة مؤقّتاً/)).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('فشل تفويض (RASTER_AUTH_FAILURE) ⇒ رسالة بلا زرّ (لا cta)', () => {
    render(<NdviUnavailableNotice info={{ code: 'RASTER_AUTH_FAILURE', retryable: false }} onProcess={() => {}} />);
    expect(screen.getByText(/تعذّر تفويض صور هذا الحقل/)).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('لا معالِج (onProcess غائب) ⇒ لا زرّ حتّى للحالة الحتميّة', () => {
    render(<NdviUnavailableNotice info={{ code: 'NO_PROCESSED_IMAGERY', retryable: false }} />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('processing=true ⇒ الزرّ مُعطَّل', () => {
    render(
      <NdviUnavailableNotice
        info={{ code: 'NO_PROCESSED_IMAGERY', retryable: false }}
        onProcess={() => {}}
        processing
      />,
    );
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('code مجهول ⇒ رسالة احتياطيّة (message ثمّ نصّ عامّ) بلا زرّ', () => {
    render(<NdviUnavailableNotice info={{ code: 'SOMETHING_NEW', message: 'سبب مخصّص', retryable: false }} />);
    expect(screen.getByText(/سبب مخصّص/)).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});
