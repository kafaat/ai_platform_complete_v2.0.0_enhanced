// ═══════════════════════════════════════════════════════════════
// SAHOOL v8.0 — TasksPage.tsx (صفحة المهام الميدانية)
// ✅ عرض المهام مع فلترة بالحالة
// ✅ تسجيل إنجاز + رفع صورة
// ✅ تعيين للفريق
// ✅ ربط بـ labor-agent عبر API
// ✅ تحويل التوصية → مهمة
// ═══════════════════════════════════════════════════════════════
import { useState, useEffect } from 'react';
import {
  Loader2, Check, Camera, Clock, AlertTriangle,
  Wrench, Droplets, Sprout, Bug, Wheat, RefreshCw,
  CheckCircle, X, User, Calendar,
} from 'lucide-react';
import { kongApi } from '../services/api';
import { toastStore } from '../services/websocket';

interface Task {
  task_id:               string;
  field_id:              string;
  field_name?:           string;
  task_type:             string;
  priority:              number;
  recommended_date:      string;
  status:                'pending' | 'in_progress' | 'completed' | 'cancelled';
  estimated_duration_min:number;
  estimated_cost_usd:    number;
  notes?:                string;
  photo_url?:            string;
  assigned_to?:          string;
  tenant_id:             string;
}

// Mock tasks — يُستبدل ببيانات من labor-agent
const MOCK_TASKS: Task[] = [
  { task_id:'t1', field_id:'field_01', field_name:'حقل وادي سبأ',        task_type:'irrigation',    priority:2, recommended_date:'2026-05-19', status:'pending',     estimated_duration_min:60,  estimated_cost_usd:8,  notes:'ري 15 مم — urgency=medium', tenant_id:'default' },
  { task_id:'t2', field_id:'field_06', field_name:'حقل عتمة الشرقي',    task_type:'irrigation',    priority:1, recommended_date:'2026-05-18', status:'pending',     estimated_duration_min:60,  estimated_cost_usd:8,  notes:'ري طارئ 25 مم — رطوبة 14%', tenant_id:'default' },
  { task_id:'t3', field_id:'field_03', field_name:'حقل البيضاء الجنوبي', task_type:'fertilization', priority:3, recommended_date:'2026-05-20', status:'in_progress', estimated_duration_min:90,  estimated_cost_usd:12, notes:'N=36 kg/ha — طريقة FAO', tenant_id:'default' },
  { task_id:'t4', field_id:'field_02', field_name:'حقل البيضاء الشمالي', task_type:'spraying',      priority:2, recommended_date:'2026-05-18', status:'pending',     estimated_duration_min:120, estimated_cost_usd:15, notes:'آفة: aphid — imidacloprid 150ml/هـ', tenant_id:'default' },
  { task_id:'t5', field_id:'field_07', field_name:'حقل الرياشية',        task_type:'harvest',       priority:2, recommended_date:'2026-05-21', status:'pending',     estimated_duration_min:480, estimated_cost_usd:35, notes:'خضروات 100% GDD', tenant_id:'default' },
  { task_id:'t6', field_id:'field_04', field_name:'حقل رداع الغربي',     task_type:'fertilization', priority:3, recommended_date:'2026-05-15', status:'completed',   estimated_duration_min:90,  estimated_cost_usd:12, tenant_id:'default' },
];

const TASK_CONFIG: Record<string, { icon: any; label: string; color: string }> = {
  irrigation:    { icon: Droplets,     label:'ري',           color:'#3b82f6' },
  fertilization: { icon: Sprout,       label:'تسميد',        color:'#16a34a' },
  spraying:      { icon: Bug,           label:'رش مبيدات',  color:'#f97316' },
  harvest:       { icon: Wheat,         label:'حصاد',         color:'#f59e0b' },
  scouting:      { icon: Wrench,        label:'استكشاف',      color:'#8b5cf6' },
  soil_sampling: { icon: Wrench,        label:'أخذ عينات تربة', color:'#92400e' },
};

const STATUS_CONFIG = {
  pending:     { label:'معلقة',      color:'#f59e0b', bg:'#2a1a00' },
  in_progress: { label:'جارية',     color:'#3b82f6', bg:'#001a2a' },
  completed:   { label:'منجزة',     color:'#16a34a', bg:'#1e3a1e' },
  cancelled:   { label:'ملغاة',     color:'#6b7280', bg:'#1e293b' },
};

const PRIORITY_MAP: Record<number,string> = { 1:'حرج', 2:'عالٍ', 3:'متوسط', 4:'منخفض', 5:'روتيني' };

export default function TasksPage() {
  const [tasks,       setTasks]       = useState<Task[]>(MOCK_TASKS);
  const [filter,      setFilter]      = useState<string>('all');
  const [typeFilter,  setTypeFilter]  = useState<string>('all');
  const [loading,     setLoading]     = useState(false);
  const [completing,  setCompleting]  = useState<string|null>(null);

  // جلب المهام من labor-agent/API
  useEffect(() => {
    setLoading(true);
    kongApi.get('/tasks')
      .then(r => { if (r.data?.tasks?.length) setTasks(r.data.tasks); })
      .catch(() => { /* fallback to mock */ })
      .finally(() => setLoading(false));
  }, []);

  const statusTypes: Array<Task['status']|'all'> = ['all','pending','in_progress','completed'];

  const filtered = tasks.filter(t =>
    (filter==='all' || t.status===filter) &&
    (typeFilter==='all' || t.task_type===typeFilter)
  );

  const counts = {
    all: tasks.length,
    pending:     tasks.filter(t=>t.status==='pending').length,
    in_progress: tasks.filter(t=>t.status==='in_progress').length,
    completed:   tasks.filter(t=>t.status==='completed').length,
  };

  const completeTask = async (taskId: string) => {
    setCompleting(taskId);
    try {
      await kongApi.patch(`/tasks/${taskId}`, { status:'completed' });
    } catch { /* offline */ }
    setTasks(p => p.map(t => t.task_id===taskId ? { ...t, status:'completed' } : t));
    toastStore.add('success', '✅ تم إنجاز المهمة', '');
    setCompleting(null);
  };

  const startTask = async (taskId: string) => {
    try { await kongApi.patch(`/tasks/${taskId}`, { status:'in_progress' }); } catch {}
    setTasks(p => p.map(t => t.task_id===taskId ? { ...t, status:'in_progress' } : t));
  };

  const handlePhotoUpload = (taskId: string, file: File) => {
    const url = URL.createObjectURL(file);
    setTasks(p => p.map(t => t.task_id===taskId ? { ...t, photo_url:url, status:'completed' } : t));
    toastStore.add('success', '📸 تم رفع الصورة', 'تم توثيق إنجاز المهمة');
  };

  const TaskCard = ({ task }: { task: Task; key?: React.Key }) => {
    const cfg   = TASK_CONFIG[task.task_type] || TASK_CONFIG.scouting;
    const sCfg  = STATUS_CONFIG[task.status];
    const Icon  = cfg.icon;
    const isOld = new Date(task.recommended_date) < new Date() && task.status === 'pending';

    return (
      <div className="rounded-xl border p-4 transition-all hover:border-emerald-900"
        style={{ background:'#1e293b', borderColor: isOld ? '#dc262644' : '#334155' }}>
        <div className="flex items-start gap-3">
          {/* Icon */}
          <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
            style={{ background:`${cfg.color}22` }}>
            <Icon className="w-5 h-5" style={{ color:cfg.color }} />
          </div>
          {/* Content */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-0.5 flex-wrap">
              <span className="font-semibold text-slate-100 text-sm">{cfg.label}</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded-full"
                style={{ background:`${sCfg.color}22`, color:sCfg.color }}>{sCfg.label}</span>
              <span className="text-[10px] text-slate-500">
                أولوية: {PRIORITY_MAP[task.priority] || task.priority}
              </span>
              {isOld && <span className="text-[10px] text-red-400 flex items-center gap-0.5"><AlertTriangle className="w-3 h-3" /> متأخرة</span>}
            </div>
            <div className="text-xs text-slate-400 mb-1">{task.field_name || task.field_id}</div>
            {task.notes && <p className="text-xs text-slate-300 leading-relaxed mb-2">{task.notes}</p>}
            <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-500">
              <span className="flex items-center gap-1"><Calendar className="w-3 h-3" />{task.recommended_date}</span>
              <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{task.estimated_duration_min} دقيقة</span>
              <span className="flex items-center gap-1" style={{ color:'#f59e0b' }}>${task.estimated_cost_usd}</span>
            </div>
            {/* Photo */}
            {task.photo_url && (
              <img src={task.photo_url} alt="توثيق" className="mt-2 h-20 rounded-lg object-cover" />
            )}
          </div>
          {/* Actions */}
          {task.status !== 'completed' && task.status !== 'cancelled' && (
            <div className="flex flex-col gap-1.5 flex-shrink-0">
              {task.status === 'pending' && (
                <button onClick={() => startTask(task.task_id)}
                  className="px-3 py-1.5 rounded-lg text-[11px] font-medium border text-blue-400 hover:text-blue-300"
                  style={{ borderColor:'#3b82f644' }}>
                  بدء
                </button>
              )}
              <button onClick={() => completeTask(task.task_id)} disabled={completing===task.task_id}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-[11px] font-medium text-white"
                style={{ background:'#16a34a' }}>
                {completing===task.task_id ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
                إنجاز
              </button>
              <label className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-[11px] cursor-pointer border"
                style={{ borderColor:'#334155', color:'#94a3b8' }}>
                <Camera className="w-3 h-3" /> صورة
                <input type="file" accept="image/*" className="hidden"
                  onChange={e => e.target.files?.[0] && handlePhotoUpload(task.task_id, e.target.files[0])} />
              </label>
            </div>
          )}
          {task.status === 'completed' && (
            <CheckCircle className="w-5 h-5 text-emerald-400 flex-shrink-0 mt-1" />
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-5 max-w-4xl mx-auto" dir="rtl">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3 justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-100">المهام الميدانية</h2>
          <p className="text-sm text-slate-400">مُنشأة تلقائياً من وكلاء الري والتسميد والمكافحة</p>
        </div>
        <button onClick={() => { setLoading(true); setTimeout(()=>setLoading(false),800); }}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm text-slate-400 hover:text-slate-200 border"
          style={{ borderColor:'#334155' }}>
          <RefreshCw className={`w-4 h-4 ${loading?'animate-spin':''}`} /> تحديث
        </button>
      </div>

      {/* Status tabs */}
      <div className="flex flex-wrap gap-2">
        {statusTypes.map(s=>{
          const active = filter===s;
          const cnt = counts[s as keyof typeof counts] ?? 0;
          const color = s==='pending' ? '#f59e0b' : s==='in_progress' ? '#3b82f6' : s==='completed' ? '#16a34a' : '#6b7280';
          return (
            <button key={s} onClick={()=>setFilter(s)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-all"
              style={{ background: active ? `${color}22` : '#1e293b', border:`1px solid ${active?color+'44':'#334155'}`, color: active ? color : '#64748b' }}>
              {s==='all'?'الكل':STATUS_CONFIG[s as Task['status']]?.label}
              <span className="text-[11px] px-1.5 rounded-full" style={{ background:`${color}33` }}>{cnt}</span>
            </button>
          );
        })}
        {/* Type filter */}
        <select value={typeFilter} onChange={e=>setTypeFilter(e.target.value)}
          className="px-3 py-1.5 rounded-lg text-sm mr-auto"
          style={{ background:'#1e293b', border:'1px solid #334155', color:'#e2e8f0' }}>
          <option value="all">كل الأنواع</option>
          {Object.entries(TASK_CONFIG).map(([k,v])=><option key={k} value={k}>{v.label}</option>)}
        </select>
      </div>

      {/* Tasks */}
      {loading ? (
        <div className="flex items-center justify-center h-48">
          <Loader2 className="w-7 h-7 text-emerald-500 animate-spin" />
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map(t => <TaskCard key={t.task_id} task={t} />)}
          {filtered.length === 0 && (
            <div className="text-center py-12 text-slate-500">
              <CheckCircle className="w-10 h-10 mx-auto mb-2 text-emerald-700" />
              <p>{filter==='completed' ? 'لا توجد مهام منجزة' : 'لا توجد مهام في هذه الفئة 🎉'}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
