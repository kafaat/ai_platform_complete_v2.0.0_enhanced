// اختبارات ImageryTimelineThumb — الحالة تُعلَن ولا تُستنتج من الفراغ.
//
// الجذر (IMAGERY-BLANK-THUMBNAIL-01): `onError` كان يضبط `style.display = 'none'`، فيصير
// كلّ فشل مربّعاً فارغاً لا يميّزه المستخدم عن «لا صورة لهذا التاريخ»؛ وتاريخ المزوّد
// المعلّق لم يكن يعرض عنصراً أصلاً. الحالتان تبدوان متطابقتين وهما مختلفتان: واحدة
// تُعالَج الآن، والأخرى أصل مُعلَن تعذّر تقديمه.
//
// الحارس الحاسم هو `لا يختفي عند الفشل` — لأنّه يمنع عودة السلوك القديم حرفيّاً.
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ImageryTimelineThumb from './ImageryTimelineThumb';

const BORDER = '#334155';

describe('ImageryTimelineThumb — حالات مرئيّة بدل إخفاء صامت', () => {
  it('بلا رابط (has_cog=false) ⇒ «قيد المعالجة» لا مساحة فارغة', () => {
    render(<ImageryTimelineThumb src={null} date="2026-06-18" borderColor={BORDER} />);
    expect(screen.getByText('قيد المعالجة')).toBeInTheDocument();
    expect(screen.queryByTestId('imagery-thumb-img')).not.toBeInTheDocument();
  });

  it('برابط ⇒ الصورة تُطلَب، وبلا نصّ حالة قبل نتيجتها', () => {
    render(<ImageryTimelineThumb src="/thumb.png" date="2026-06-18" borderColor={BORDER} />);
    expect(screen.getByTestId('imagery-thumb-img')).toHaveAttribute('src', '/thumb.png');
    expect(screen.queryByText('قيد المعالجة')).not.toBeInTheDocument();
    expect(screen.queryByText('تعذّر العرض')).not.toBeInTheDocument();
  });

  it('نجاح التحميل ⇒ الصورة تبقى بلا أيّ نصّ حالة', () => {
    render(<ImageryTimelineThumb src="/thumb.png" date="2026-06-18" borderColor={BORDER} />);
    fireEvent.load(screen.getByTestId('imagery-thumb-img'));
    expect(screen.getByTestId('imagery-thumb-img')).toBeInTheDocument();
    expect(screen.queryByText('تعذّر العرض')).not.toBeInTheDocument();
  });

  it('فشل التحميل (404 من المسار المُدَام) ⇒ «تعذّر العرض» مرئيّة', () => {
    render(<ImageryTimelineThumb src="/thumb.png" date="2026-06-18" borderColor={BORDER} />);
    fireEvent.error(screen.getByTestId('imagery-thumb-img'));
    expect(screen.getByText('تعذّر العرض')).toBeInTheDocument();
  });

  it('حارس انحدار: لا يختفي عند الفشل — لا display:none ولا عنصر فارغ', () => {
    const { container } = render(
      <ImageryTimelineThumb src="/thumb.png" date="2026-06-18" borderColor={BORDER} />,
    );
    fireEvent.error(screen.getByTestId('imagery-thumb-img'));

    // السلوك القديم: العنصر يبقى في الشجرة بـdisplay:none فيقرأه المستخدم كفراغ.
    const hidden = container.querySelectorAll('[style*="display: none"]');
    expect(hidden).toHaveLength(0);
    expect(container).not.toBeEmptyDOMElement();
    expect(screen.getByTestId('imagery-thumb-failed')).toBeInTheDocument();
  });

  it('تبدّل الرابط بعد فشل ⇒ تُعاد المحاولة، ولا تُورَّث حالة الفشل لصورة أخرى', () => {
    const { rerender } = render(
      <ImageryTimelineThumb src="/a.png" date="2026-06-18" borderColor={BORDER} />,
    );
    fireEvent.error(screen.getByTestId('imagery-thumb-img'));
    expect(screen.getByText('تعذّر العرض')).toBeInTheDocument();

    rerender(<ImageryTimelineThumb src="/b.png" date="2026-06-18" borderColor={BORDER} />);
    expect(screen.getByTestId('imagery-thumb-img')).toHaveAttribute('src', '/b.png');
    expect(screen.queryByText('تعذّر العرض')).not.toBeInTheDocument();
  });

  it('الانتقال إلى تاريخ بلا أصل ⇒ يعود إلى «قيد المعالجة»', () => {
    const { rerender } = render(
      <ImageryTimelineThumb src="/a.png" date="2026-06-18" borderColor={BORDER} />,
    );
    rerender(<ImageryTimelineThumb src={null} date="2026-06-21" borderColor={BORDER} />);
    expect(screen.getByText('قيد المعالجة')).toBeInTheDocument();
  });
});
