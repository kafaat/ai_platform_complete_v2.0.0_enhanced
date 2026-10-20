import {
  CC_BY_4_LABEL,
  CC_BY_4_URL,
  OPEN_METEO_CREDIT_TEXT,
  OPEN_METEO_URL,
} from '../lib/openMeteoAttribution';

/**
 * سطرُ نسبة بيانات الطقس — يوضَع بجوار كلّ عرضٍ لبيانات Open-Meteo (CC BY 4.0 تشترط
 * رابط نسبة ورابط الرخصة). `<span>` كتليّ لا `<p>` كي يصحّ داخل أيّ حاوية نصّيّة.
 * النصّ لاتينيّ بـ`dir="ltr"` لأنّه الصيغة التي يطلبها المصدر حرفيّاً.
 */
export function OpenMeteoAttribution({ className = '' }: { className?: string }) {
  return (
    <span
      dir="ltr"
      data-testid="open-meteo-attribution"
      className={`block text-[10px] leading-snug text-slate-500 ${className}`.trim()}
    >
      <a href={OPEN_METEO_URL} target="_blank" rel="noopener noreferrer" className="underline hover:text-slate-300">
        {OPEN_METEO_CREDIT_TEXT}
      </a>
      {' · '}
      <a href={CC_BY_4_URL} target="_blank" rel="noopener noreferrer" className="underline hover:text-slate-300">
        {CC_BY_4_LABEL}
      </a>
    </span>
  );
}
