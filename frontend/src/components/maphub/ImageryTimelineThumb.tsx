import { useEffect, useState } from 'react';

/**
 * مصغّرة بطاقة السجلّ الزمنيّ — بحالة مرئيّة بدل إخفاء صامت.
 *
 * `IMAGERY-BLANK-THUMBNAIL-01`. كان `onError` يضبط `style.display = 'none'`، فيتحوّل كلّ
 * فشل إلى مربّع فارغ لا يميّزه المستخدم عن «لا صورة لهذا التاريخ». وتاريخ المزوّد المعلّق
 * (`has_cog=false`) لم يكن يعرض عنصراً أصلاً. الحالتان تبدوان متطابقتين وهما مختلفتان
 * تماماً: واحدة تعالَج الآن، والأخرى أصل مُعلَن تعذّر تقديمه.
 *
 * لذلك تُعلَن الحالة ولا تُستنتج من الفراغ:
 *   - `pending` — مرّ القمر ولم يُعالَج بعد (`has_cog=false`).
 *   - `ready`   — الأصل المُدَام حُمِّل وعُرِض.
 *   - `failed`  — الأصل مُعلَن وتعذّر تقديمه (المسار المُدَام يعيد 404 ⇒ `onError`).
 */
export type ThumbState = 'pending' | 'loading' | 'ready' | 'failed';

export interface ImageryTimelineThumbProps {
  /** رابط المصغّرة — `null` حين لا أصل مُعلَن (تاريخ مزوّد معلّق). */
  src: string | null;
  date: string;
  /** لون الحدّ حسب حالة الاختيار في البطاقة. */
  borderColor: string;
}

const BOX = 'mb-2 h-16 w-full overflow-hidden rounded-lg border';

export function ImageryTimelineThumb({ src, date, borderColor }: ImageryTimelineThumbProps) {
  const [state, setState] = useState<ThumbState>(src ? 'loading' : 'pending');

  // تبدّل الرابط (تغيّر المؤشّر/المستأجِر) يعيد الحالة — وإلّا بقي `failed` لصورة أخرى.
  useEffect(() => {
    setState(src ? 'loading' : 'pending');
  }, [src]);

  const label =
    state === 'pending' ? 'قيد المعالجة' : state === 'failed' ? 'تعذّر العرض' : null;

  return (
    <div className={BOX} style={{ borderColor, background: '#020617' }} data-testid="imagery-thumb">
      {src && state !== 'failed' && (
        <img
          src={src}
          alt={`مصغّرة صورة الحقل ${date}`}
          className="h-full w-full object-cover"
          loading="lazy"
          data-testid="imagery-thumb-img"
          onLoad={() => setState('ready')}
          // 404 من المسار المُدَام (أصل مُعلَن غير قابل للتقديم) يصل هنا. لا نُخفي
          // العنصر — نستبدله بحالة مقروءة، فالفشل يُرى ولا يُبتلَع.
          onError={() => setState('failed')}
        />
      )}
      {label && (
        <div
          className="flex h-full w-full items-center justify-center text-[10px]"
          style={{ color: state === 'failed' ? '#fca5a5' : '#94a3b8' }}
          data-testid={`imagery-thumb-${state}`}
        >
          {label}
        </div>
      )}
    </div>
  );
}

export default ImageryTimelineThumb;
