// شارة «عرض تجريبيّ» — تُعرَض حين تحوي الشاشة بيانات ديمو (real_data===false).
// صدق بصريّ: يميّز الديمو عن الإنتاج كي لا يُخلَط أحدهما بالآخر.
interface DemoBadgeProps {
  className?: string;
  label?: string;
}

export default function DemoBadge({ className = '', label = 'عرض تجريبيّ' }: DemoBadgeProps) {
  return (
    <span
      dir="rtl"
      data-testid="demo-badge"
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${className}`}
      style={{ background: '#78350f', color: '#fcd34d', border: '1px solid #b45309' }}
      title="بيانات تجريبيّة — لا تُستخدَم في القرار/التوصية/الاقتصاد"
    >
      🧪 {label}
    </span>
  );
}
