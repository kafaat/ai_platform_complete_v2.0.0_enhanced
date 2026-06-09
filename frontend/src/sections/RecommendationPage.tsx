import { useState } from "react";

// ════════════════════════════════════════════════════════════
// SAHOOL — صفحة التوصية المتكاملة (Recommendation View)
// تعرض مخرجات core/recommendation_engine.py (المايسترو):
//   • FarmerView: القرار + السبب + الثقة + التنبيهات (ما يراه المزارع)
//   • BackendDetail: المؤشرات الخام (مخفية، تظهر بزر للمهندس)
//   • حالة BLOCKED: لا توصية عمياء — يطلب البيانات الناقصة
// يطابق منطق المايسترو: الثقة = أضعف حلقة، الإنتاج null حتى المعايرة.
// ════════════════════════════════════════════════════════════

// سيناريوهات تحاكي مخرجات المايسترو الفعلية
const SCENARIOS = {
  blocked: {
    label: "مثال توضيحي",
    status: "blocked",
    signal: { icon: "⚪", text: "بيانات ناقصة", color: "#9cb8a3" },
    headline: "لا يمكن إصدار توصية بعد",
    reason: "بيانات ضرورية ناقصة: ملوحة التربة، حموضة pH، ملوحة مياه الري، فترة أمان المبيد",
    confidence: "—",
    alerts: ["⚠️ مطلوب: تحاليل التربة (S3, S4) ومياه الري (I3)"],
    nextAction: "أدخل تحاليل التربة لتفعيل التوصية",
    backend: {
      grade: "BLOCKED", governing: ["S3", "S4", "I3", "L3"],
      missing: ["C1", "C5", "S3", "S4", "I1", "I3", "L3"],
      et0: null, etc: null, irrigation: null, suitability: null, yield: null,
      zoneFactor: null, zoneStatus: "pending",
    },
  },
  issued: {
    label: "لو توفّرت البيانات",
    status: "issued",
    signal: { icon: "🟢", text: "جيد", color: "#5cbf6e" },
    headline: "اروِ بما يعادل ٣٥ مم",
    reason: "حساب الاحتياج المائي حسب الطقس ومرحلة المحصول (FAO-56)",
    confidence: "ثقة متوسطة (النموذج عام، لم يُعاير محلياً بعد)",
    alerts: [],
    nextAction: "المعايرة الإقليمية قيد الاكتمال (تحتاج ٥ مزارع)",
    backend: {
      grade: "MEDIUM", governing: [], missing: [],
      et0: 10.14, etc: 8.5, irrigation: 350, suitability: "S2", yield: null,
      zoneFactor: null, zoneStatus: "pending",
    },
  },
  danger: {
    label: "محصول غير ملائم",
    status: "issued",
    signal: { icon: "🔴", text: "خطر", color: "#d4593a" },
    headline: "هذا المحصول غير ملائم لظروف التربة",
    reason: "ملوحة التربة تتجاوز تحمّل المحصول — الحاكم الصارم يمنع",
    confidence: "ثقة عالية (تحليل مخبري مؤكّد)",
    alerts: ["🔴 ملوحة EC = ١٢ ds/m تتجاوز تحمّل القمح (٦)", "💡 بدائل متحمّلة: الشعير (٨)، السورغم (٦.٨)"],
    nextAction: "اختر محصولاً متحمّلاً للملوحة، أو حسّن التربة بالغسيل",
    backend: {
      grade: "HIGH", governing: [], missing: [],
      et0: 9.8, etc: 7.2, irrigation: 290, suitability: "N", yield: null,
      zoneFactor: 0.88, zoneStatus: "pending",
    },
  },
};

export default function RecommendationView() {
  const [scen, setScen] = useState<keyof typeof SCENARIOS>("blocked");
  const [showBackend, setShowBackend] = useState(false);
  const s = SCENARIOS[scen];

  return (
    <div dir="rtl" style={{
      fontFamily: "'Noto Kufi Arabic', system-ui, sans-serif",
      background: "linear-gradient(160deg, #14201a 0%, #1c2b22 100%)",
      minHeight: "100vh", color: "#e8eee9", padding: 24,
    }}>
      <style>{`@import url('https://fonts.googleapis.com/css2?family=Noto+Kufi+Arabic:wght@400;600;800&display=swap');`}</style>

      {/* العنوان */}
      <div style={{ marginBottom: 20, borderBottom: "2px solid #2d4a37", paddingBottom: 16 }}>
        <div style={{ fontSize: 13, color: "#7fae8c", letterSpacing: 1, fontWeight: 600 }}>
          سهول · التوصية المتكاملة
        </div>
        <h1 style={{ fontSize: 26, fontWeight: 800, margin: "4px 0 0", color: "#fff" }}>
          الحقل المحدّد · مثال
        </h1>
      </div>

      {/* مبدّل السيناريو (للتوضيح) */}
      <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
        {(Object.entries(SCENARIOS) as [keyof typeof SCENARIOS, typeof SCENARIOS[keyof typeof SCENARIOS]][]).map(([k, v]) => (
          <button key={k} onClick={() => setScen(k)}
            style={{
              padding: "8px 16px", borderRadius: 20, cursor: "pointer", fontFamily: "inherit",
              border: scen === k ? "2px solid #5cbf6e" : "1px solid #2d4a37",
              background: scen === k ? "#1f3a2a" : "transparent",
              color: scen === k ? "#fff" : "#9cb8a3", fontSize: 12, fontWeight: 600,
            }}>{v.label}</button>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 16, maxWidth: 620 }}>
        {/* بطاقة المزارع (FarmerView) */}
        <div style={{
          background: "#1a2b21", borderRadius: 16, padding: 24,
          border: `2px solid ${s.signal.color}33`,
          boxShadow: "0 8px 32px rgba(0,0,0,.3)",
        }}>
          {/* الإشارة */}
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
            <span style={{ fontSize: 32 }}>{s.signal.icon}</span>
            <span style={{
              fontSize: 14, fontWeight: 700, color: s.signal.color,
              background: `${s.signal.color}22`, padding: "4px 14px", borderRadius: 20,
            }}>{s.signal.text}</span>
          </div>

          {/* العنوان الرئيسي (القرار) */}
          <div style={{ fontSize: 24, fontWeight: 800, color: "#fff", marginBottom: 12, lineHeight: 1.4 }}>
            {s.headline}
          </div>

          {/* السبب */}
          <div style={{ fontSize: 14, color: "#cdddd2", lineHeight: 1.7, marginBottom: 16 }}>
            <span style={{ color: "#7fae8c", fontWeight: 600 }}>السبب: </span>{s.reason}
          </div>

          {/* الثقة */}
          {s.confidence !== "—" && (
            <div style={{
              fontSize: 13, color: "#9cb8a3", background: "#0d1611",
              borderRadius: 8, padding: "8px 14px", marginBottom: 14,
            }}>📊 {s.confidence}</div>
          )}

          {/* التنبيهات */}
          {s.alerts.map((a, i) => (
            <div key={i} style={{
              fontSize: 13, color: "#e8eee9", background: a.startsWith("🔴") ? "#3a1f1a" : a.startsWith("💡") ? "#2a3d1f" : "#3a2f1a",
              borderRadius: 8, padding: "10px 14px", marginBottom: 8,
              borderRight: `3px solid ${a.startsWith("🔴") ? "#d4593a" : a.startsWith("💡") ? "#5cbf6e" : "#d4a017"}`,
            }}>{a}</div>
          ))}

          {/* الخطوة التالية */}
          <div style={{
            marginTop: 16, paddingTop: 16, borderTop: "1px solid #2d4a37",
            fontSize: 13, color: "#7fae8c",
          }}>
            <span style={{ fontWeight: 600 }}>الخطوة التالية: </span>{s.nextAction}
          </div>
        </div>

        {/* زر إظهار Backend */}
        <button onClick={() => setShowBackend(!showBackend)}
          style={{
            padding: "10px", borderRadius: 10, cursor: "pointer", fontFamily: "inherit",
            background: "transparent", border: "1px dashed #2d4a37",
            color: "#7fae8c", fontSize: 12, fontWeight: 600,
          }}>
          {showBackend ? "▲ إخفاء التفاصيل التقنية" : "▼ عرض التفاصيل التقنية (للمهندس)"}
        </button>

        {/* تفاصيل Backend (مخفية افتراضياً) */}
        {showBackend && (
          <div style={{
            background: "#0d1611", borderRadius: 14, padding: 20,
            border: "1px solid #2d4a37", fontFamily: "monospace", fontSize: 13,
          }}>
            <div style={{ color: "#7fae8c", fontWeight: 600, marginBottom: 14, fontFamily: "'Noto Kufi Arabic'" }}>
              مخرجات Backend (لا تُعرض للمزارع)
            </div>
            <Row k="درجة الجودة" v={s.backend.grade} c={s.backend.grade === "BLOCKED" ? "#d4593a" : s.backend.grade === "HIGH" ? "#5cbf6e" : "#d4a017"} />
            {s.backend.governing.length > 0 && <Row k="حاكمات مانعة" v={s.backend.governing.join(", ")} c="#d4593a" />}
            {s.backend.missing.length > 0 && <Row k="مراصد ناقصة" v={s.backend.missing.join(", ")} c="#9cb8a3" />}
            <div style={{ height: 1, background: "#2d4a37", margin: "12px 0" }} />
            <Row k="ET₀ (mm)" v={s.backend.et0 ?? "—"} />
            <Row k="ETc (mm)" v={s.backend.etc ?? "—"} />
            <Row k="الري (m³/ha)" v={s.backend.irrigation ?? "—"} />
            <Row k="الملاءمة" v={s.backend.suitability ?? "—"} c={s.backend.suitability === "N" ? "#d4593a" : "#cdddd2"} />
            <Row k="zone_factor" v={s.backend.zoneFactor ?? "null"} />
            <Row k="حالة المعايرة" v={s.backend.zoneStatus} />
            <div style={{ height: 1, background: "#2d4a37", margin: "12px 0" }} />
            <Row k="الإنتاج المتوقّع" v={s.backend.yield ?? "null (لا رقم وهمي)"} c="#d4a017" />
          </div>
        )}
      </div>

      {/* تذييل: مبدأ الفصل */}
      <div style={{
        marginTop: 24, padding: 14, borderRadius: 10, background: "#0d1611",
        border: "1px dashed #2d4a37", fontSize: 11, color: "#7fae8c",
        textAlign: "center", maxWidth: 620,
      }}>
        المزارع يرى القرار + السبب + الثقة · الـ backend يحمل المعادلات والنسب ·
        الإنتاج يبقى null حتى المعايرة الفعلية — لا رقم وهمي.
      </div>
    </div>
  );
}

function Row({ k, v, c = "#cdddd2" }: { k: React.ReactNode; v: React.ReactNode; c?: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "5px 0" }}>
      <span style={{ color: "#7fae8c", fontFamily: "'Noto Kufi Arabic'" }}>{k}</span>
      <span style={{ color: c, fontWeight: 600 }}>{String(v)}</span>
    </div>
  );
}
