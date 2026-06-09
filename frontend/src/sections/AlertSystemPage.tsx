// ═══════════════════════════════════════════════════════════════
// SAHOOL v8.0 — AlertSystemPage
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import { Bell, CheckCircle, AlertTriangle, AlertOctagon, Info, Check, X, Filter } from 'lucide-react';

interface Alert {
  id: string; severity: 'critical'|'high'|'medium'|'low';
  title: string; message: string; field: string;
  indicator: string; value: number; threshold: number;
  time: string; acknowledged: boolean;
}

const INITIAL_ALERTS: Alert[] = [
  { id:'a1', severity:'critical', title:'إجهاد مائي حرج',    message:'NDVI انخفض إلى 0.28 — تدخل فوري مطلوب',       field:'حقل عتمة الشرقي',    indicator:'NDVI',      value:0.28, threshold:0.35, time:'منذ 30 دقيقة', acknowledged:false },
  { id:'a2', severity:'high',     title:'رطوبة تربة منخفضة', message:'رطوبة التربة 14% أقل من الحد الأدنى 20%',      field:'حقل البيضاء الجنوبي',indicator:'رطوبة',    value:14,   threshold:20,  time:'منذ 2 ساعة',   acknowledged:false },
  { id:'a3', severity:'high',     title:'إجهاد حراري',        message:'درجة الحرارة 41°C تجاوزت الحد الحرج للقمح',   field:'حقل ذي السفال',      indicator:'حرارة',    value:41,   threshold:38,  time:'منذ 4 ساعات',  acknowledged:false },
  { id:'a4', severity:'medium',   title:'نقص نيتروجين',       message:'محتوى N في التربة 12 mg/kg أقل من المطلوب',    field:'حقل وادي سبأ',       indicator:'نيتروجين', value:12,   threshold:20,  time:'منذ 8 ساعات',  acknowledged:false },
  { id:'a5', severity:'medium',   title:'ملوحة مرتفعة',       message:'EC التربة 3.2 dS/m — تحذير من الملوحة',        field:'حقل رداع الغربي',    indicator:'EC',       value:3.2,  threshold:2.0, time:'منذ 1 يوم',    acknowledged:true  },
  { id:'a6', severity:'low',      title:'توقعات هطول أمطار',  message:'هطول 25mm متوقع خلال 48 ساعة',                field:'جميع الحقول',         indicator:'طقس',      value:25,   threshold:0,   time:'منذ 6 ساعات',  acknowledged:false },
  { id:'a7', severity:'low',      title:'موعد التسميد',        message:'موعد التسميد البوتاسي لحقل الشعير غداً',       field:'حقل البيضاء الشمالي',indicator:'جدول',     value:0,    threshold:0,   time:'منذ 12 ساعة',  acknowledged:true  },
];

const SEVERITY_CONFIG = {
  critical:{ label:'حرج',    icon:AlertOctagon, color:'#dc2626', bg:'#1a0000', border:'#dc262633' },
  high:    { label:'عالي',   icon:AlertTriangle,color:'#f97316', bg:'#1a0800', border:'#f9731633' },
  medium:  { label:'متوسط',  icon:AlertTriangle,color:'#f59e0b', bg:'#1a1000', border:'#f59e0b33' },
  low:     { label:'منخفض',  icon:Info,         color:'#38bdf8', bg:'#00101a', border:'#38bdf833' },
};

export function AlertSystemPage() {
  const [alerts, setAlerts] = useState<Alert[]>(INITIAL_ALERTS);
  const [filter, setFilter] = useState<string>('all');
  const [showAcknowledged, setShowAcknowledged] = useState(false);

  const filtered = alerts.filter(a =>
    (filter === 'all' || a.severity === filter) &&
    (showAcknowledged || !a.acknowledged)
  );

  const acknowledge = (id: string) =>
    setAlerts(prev => prev.map(a => a.id === id ? { ...a, acknowledged:true } : a));
  const dismiss = (id: string) =>
    setAlerts(prev => prev.filter(a => a.id !== id));

  const counts = { critical:0, high:0, medium:0, low:0 };
  alerts.filter(a => !a.acknowledged).forEach(a => counts[a.severity]++);

  return (
    <div className="space-y-5 max-w-4xl mx-auto" dir="rtl">
      <div className="flex flex-wrap items-center gap-3 justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-100">نظام التنبيهات</h2>
          <p className="text-sm text-slate-400">{alerts.filter(a=>!a.acknowledged).length} تنبيه نشط</p>
        </div>
        <label className="flex items-center gap-2 text-sm text-slate-400 cursor-pointer">
          <input type="checkbox" checked={showAcknowledged} onChange={e => setShowAcknowledged(e.target.checked)}
            className="w-4 h-4 accent-emerald-500" />
          عرض المُعترف بها
        </label>
      </div>

      {/* Severity summary */}
      <div className="grid grid-cols-4 gap-3">
        {(Object.entries(SEVERITY_CONFIG) as any[]).map(([key, cfg]) => {
          const Icon = cfg.icon;
          return (
            <button key={key} onClick={() => setFilter(filter===key ? 'all' : key)}
              className="rounded-xl p-3 border text-center transition-all hover:scale-[1.02]"
              style={{ background:filter===key ? cfg.bg : '#1e293b', borderColor:filter===key ? cfg.color : '#334155' }}>
              <Icon className="w-5 h-5 mx-auto mb-1" style={{ color:cfg.color }} />
              <div className="text-xl font-bold" style={{ color:cfg.color }}>{counts[key as keyof typeof counts]}</div>
              <div className="text-[10px] text-slate-400">{cfg.label}</div>
            </button>
          );
        })}
      </div>

      {/* Alert list */}
      <div className="space-y-3">
        {filtered.length === 0 && (
          <div className="text-center py-12 text-slate-500">
            <CheckCircle className="w-10 h-10 mx-auto mb-2 text-emerald-700" />
            <p>لا توجد تنبيهات نشطة 🎉</p>
          </div>
        )}
        {filtered.map(a => {
          const cfg = SEVERITY_CONFIG[a.severity];
          const Icon = cfg.icon;
          return (
            <div key={a.id} className="rounded-xl p-4 border transition-all"
              style={{ background:a.acknowledged ? '#1e293b' : cfg.bg, borderColor:a.acknowledged ? '#334155' : cfg.border, opacity:a.acknowledged ? 0.6 : 1 }}>
              <div className="flex items-start gap-3">
                <Icon className="w-5 h-5 mt-0.5 flex-shrink-0" style={{ color:cfg.color }} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-semibold text-slate-100 text-sm">{a.title}</span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full" style={{ background:`${cfg.color}22`, color:cfg.color }}>{cfg.label}</span>
                    {a.acknowledged && <span className="text-[10px] text-emerald-500">✓ مُعترف بها</span>}
                  </div>
                  <p className="text-xs text-slate-300 mb-2">{a.message}</p>
                  <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-500">
                    <span>📍 {a.field}</span>
                    <span>📊 {a.indicator}: {a.value} {'>'} {a.threshold}</span>
                    <span>⏱ {a.time}</span>
                  </div>
                </div>
                {!a.acknowledged && (
                  <div className="flex gap-1.5">
                    <button onClick={() => acknowledge(a.id)}
                      className="p-1.5 rounded-lg hover:bg-emerald-950 text-slate-400 hover:text-emerald-400 transition-colors">
                      <Check className="w-4 h-4" />
                    </button>
                    <button onClick={() => dismiss(a.id)}
                      className="p-1.5 rounded-lg hover:bg-red-950 text-slate-400 hover:text-red-400 transition-colors">
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
export default AlertSystemPage;
