import { useState, type CSSProperties, type ReactNode } from "react";

// ════════════════════════════════════════════════════════════
// SAHOOL — معالج إعداد الحقل الكامل (6 خطوات)
// يطابق المخطط الانسيابي المعتمد + نقاط الصدق:
//   موقع → موسم → محصول → تربة → ري → مراجعة
// نقطة الصدق: "توقّع الإنتاجية" اختياري وبلا رقم وهمي —
//   يُستبدل بحقل الحصاد الفعلي (يُملأ نهاية الموسم للمعايرة).
// عربي أصيل RTL · كشف شرطي · تحقّق فوري · بوابة جودة → BLOCKED/جاهز
// ════════════════════════════════════════════════════════════

const YEMEN = { lat: [12, 19], lon: [42, 55] };
const SOIL_TYPES = ["طينية (Clay)", "رملية (Sandy)", "طميية (Loam)", "طينية رملية", "طميية طينية", "غرينية (Silt)"];
const IRRIGATION: Record<string, { label: string; extra: string[] }> = {
  pivot: { label: "محوري (Pivot)", extra: ["length", "controller", "flow", "runtime"] },
  drip: { label: "تنقيط (Drip)", extra: ["flow", "spacing"] },
  sprinkler: { label: "رش (Sprinkler)", extra: ["flow"] },
  furrow: { label: "غمر/أحواض (Furrow)", extra: ["flow"] },
  none: { label: "بعلي (بلا ري)", extra: [] },
};
const CROPS = ["قمح (سخا)", "قمح شتوي", "شعير", "ذرة رفيعة (سورغم)", "طماطم", "بطاطس", "العلس (محلي)", "أخرى"];
const SEASONS = ["الموسم الشتوي ٢٠٢٥/٢٠٢٦", "الموسم الصيفي ٢٠٢٦", "موسم مخصّص"];
const STEPS = [
  { id: 1, icon: "📍", title: "الموقع" }, { id: 2, icon: "📅", title: "الموسم" },
  { id: 3, icon: "🌱", title: "المحصول" }, { id: 4, icon: "🧪", title: "التربة" },
  { id: 5, icon: "💧", title: "الري" }, { id: 6, icon: "✓", title: "مراجعة" },
];

export default function FieldSetupWizard() {
  const [step, setStep] = useState(1);
  const [d, setD] = useState({
    name: "", lat: "", lon: "", area: "", manager: "", importMethod: "draw",
    season: "", seasonStart: "", seasonEnd: "", crop: "", variety: "", plantingDate: "", gdd: "",
    soilType: "", salinity: "", ph: "", om: "", waterSalinity: "",
    irrigation: "", length: "", controller: "", flow: "", runtime: "",
  });
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const set = (k: string, v: string) => setD((p) => ({ ...p, [k]: v }));
  const touch = (k: string) => setTouched((t) => ({ ...t, [k]: true }));

  const err: Record<string, string> = {};
  if (step === 1) {
    if (!d.name.trim()) err.name = "مطلوب";
    const lat = parseFloat(d.lat), lon = parseFloat(d.lon);
    if (!d.lat) err.lat = "مطلوب"; else if (isNaN(lat) || lat < YEMEN.lat[0] || lat > YEMEN.lat[1]) err.lat = `خارج اليمن (${YEMEN.lat[0]}–${YEMEN.lat[1]}°)`;
    if (!d.lon) err.lon = "مطلوب"; else if (isNaN(lon) || lon < YEMEN.lon[0] || lon > YEMEN.lon[1]) err.lon = `خارج اليمن (${YEMEN.lon[0]}–${YEMEN.lon[1]}°)`;
  }
  if (step === 2 && !d.season) err.season = "اختر الموسم";
  if (step === 3) { if (!d.crop) err.crop = "اختر المحصول"; if (!d.plantingDate) err.plantingDate = "مطلوب"; }
  if (step === 5 && !d.irrigation) err.irrigation = "اختر نظام الري";
  const ok = Object.keys(err).length === 0;
  const soilComplete = d.salinity && d.ph && d.waterSalinity;
  const ph = parseFloat(d.ph);
  const phWarn = d.ph && (ph < 0 || ph > 14) ? "pH بين 0–14" : (d.ph && (ph < 5.5 || ph > 8.5) ? "⚠ خارج المعتاد (5.5–8.5)" : "");

  return (
    <div dir="rtl" style={{ fontFamily: "'Noto Kufi Arabic', system-ui, sans-serif", background: "linear-gradient(160deg, #14201a 0%, #1c2b22 100%)", minHeight: "100vh", color: "#e8eee9", padding: 20 }}>
      <style>{`@import url('https://fonts.googleapis.com/css2?family=Noto+Kufi+Arabic:wght@400;600;800&display=swap');input,select{font-family:inherit}input::placeholder{color:#5a7263}`}</style>

      <div style={{ maxWidth: 580, margin: "0 auto 16px" }}>
        <div style={{ fontSize: 13, color: "#7fae8c", fontWeight: 600 }}>سهول · إعداد حقل</div>
        <h1 style={{ fontSize: 22, fontWeight: 800, margin: "2px 0 0", color: "#fff" }}>مزرعة السنيدار</h1>
      </div>

      <div style={{ display: "flex", gap: 5, maxWidth: 580, margin: "0 auto 20px" }}>
        {STEPS.map((s) => (
          <div key={s.id} style={{ flex: 1, textAlign: "center" }}>
            <div style={{ height: 4, borderRadius: 2, marginBottom: 5, background: s.id <= step ? "#5cbf6e" : "#2d4a37", transition: "background .3s" }} />
            <div style={{ fontSize: 10, color: s.id === step ? "#5cbf6e" : s.id < step ? "#7fae8c" : "#5a7263", fontWeight: s.id === step ? 700 : 400 }}>{s.id < step ? "✓" : s.icon} {s.title}</div>
          </div>
        ))}
      </div>

      <div style={{ maxWidth: 580, margin: "0 auto", background: "#1a2b21", borderRadius: 16, padding: 22, border: "1px solid #2d4a37", boxShadow: "0 8px 32px rgba(0,0,0,.3)" }}>
        {step === 1 && (<div>
          <H icon="📍" t="الموقع والحدود" s="حدّد الحقل بالرسم أو رفع ملف جغرافي" />
          <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
            {[["draw", "رسم على الخريطة"], ["upload", "رفع Shapefile/KML"]].map(([k, lbl]) => (
              <button key={k} onClick={() => set("importMethod", k)} style={{ flex: 1, padding: "10px", borderRadius: 10, cursor: "pointer", fontFamily: "inherit", fontSize: 13, border: d.importMethod === k ? "2px solid #5cbf6e" : "1px solid #2d4a37", background: d.importMethod === k ? "#1f3a2a" : "transparent", color: d.importMethod === k ? "#fff" : "#9cb8a3", fontWeight: 600 }}>{lbl}</button>
            ))}
          </div>
          <F label="اسم الحقل" e={touched.name && err.name}><input value={d.name} onChange={(e) => set("name", e.target.value)} onBlur={() => touch("name")} placeholder="محوري ١" style={inp(touched.name && err.name)} /></F>
          <div style={{ display: "flex", gap: 10 }}>
            <F label="خط العرض" e={touched.lat && err.lat}><input value={d.lat} onChange={(e) => set("lat", e.target.value)} onBlur={() => touch("lat")} placeholder="16.0887" inputMode="decimal" style={inp(touched.lat && err.lat)} /></F>
            <F label="خط الطول" e={touched.lon && err.lon}><input value={d.lon} onChange={(e) => set("lon", e.target.value)} onBlur={() => touch("lon")} placeholder="44.9431" inputMode="decimal" style={inp(touched.lon && err.lon)} /></F>
          </div>
          <F label="المساحة (هكتار)"><input value={d.area} onChange={(e) => set("area", e.target.value)} placeholder={d.importMethod === "draw" ? "تُحسب تلقائياً من الرسم" : "تُقرأ من الملف"} inputMode="decimal" style={inp(false)} /></F>
          <F label="الشخص المسؤول — اختياري"><select value={d.manager} onChange={(e) => set("manager", e.target.value)} style={inp(false)}><option value="">— اختر —</option><option>عبدالسلام (مدير)</option><option>مراقب الحقل</option></select></F>
        </div>)}

        {step === 2 && (<div>
          <H icon="📅" t="الموسم الزراعي" s="حدّد الموسم — يربط المحصول بفترته الزمنية" />
          <F label="الموسم" e={touched.season && err.season}><select value={d.season} onChange={(e) => { set("season", e.target.value); touch("season"); }} style={inp(touched.season && err.season)}><option value="">— اختر —</option>{SEASONS.map((s) => <option key={s}>{s}</option>)}</select></F>
          <div style={{ display: "flex", gap: 10 }}>
            <F label="بداية الموسم"><input type="date" value={d.seasonStart} onChange={(e) => set("seasonStart", e.target.value)} style={inp(false)} /></F>
            <F label="نهاية الموسم"><input type="date" value={d.seasonEnd} onChange={(e) => set("seasonEnd", e.target.value)} style={inp(false)} /></F>
          </div>
          <div style={hint}>💡 تحديد الموسم بتواريخه يجعل حلقة المعايرة دقيقة — كل موسم يُقارن بحصاده الفعلي.</div>
        </div>)}

        {step === 3 && (<div>
          <H icon="🌱" t="المحصول" s="بيانات المحصول لحساب الاحتياج المائي ومراحل النمو (WOFOST)" />
          <F label="نوع المحصول" e={touched.crop && err.crop}><select value={d.crop} onChange={(e) => { set("crop", e.target.value); touch("crop"); }} style={inp(touched.crop && err.crop)}><option value="">— اختر —</option>{CROPS.map((c) => <option key={c}>{c}</option>)}</select></F>
          <F label="الصنف — اختياري"><input value={d.variety} onChange={(e) => set("variety", e.target.value)} placeholder="سخا ٩٤" style={inp(false)} /></F>
          <div style={{ display: "flex", gap: 10 }}>
            <F label="تاريخ الزراعة" e={touched.plantingDate && err.plantingDate}><input type="date" value={d.plantingDate} onChange={(e) => { set("plantingDate", e.target.value); touch("plantingDate"); }} style={inp(touched.plantingDate && err.plantingDate)} /></F>
            <F label="GDD للنضج — اختياري"><input value={d.gdd} onChange={(e) => set("gdd", e.target.value)} placeholder="2200" inputMode="decimal" style={inp(false)} /></F>
          </div>
        </div>)}

        {step === 4 && (<div>
          <H icon="🧪" t="التربة والمياه" s="التحاليل الحاكمة تُفعّل التوصيات — مفتاح رفع BLOCKED" />
          <div style={{ background: soilComplete ? "#1f3a2a" : "#3a2f1a", borderRadius: 10, padding: "10px 14px", marginBottom: 16, fontSize: 12, borderRight: `3px solid ${soilComplete ? "#5cbf6e" : "#d4a017"}`, color: "#cdddd2" }}>{soilComplete ? "✅ التحاليل الحاكمة كاملة — ستُفعّل التوصيات" : "⚠️ بدون S3+S4+I3 يبقى الحقل BLOCKED (لا توصية عمياء)"}</div>
          <F label="نوع التربة"><select value={d.soilType} onChange={(e) => set("soilType", e.target.value)} style={inp(false)}><option value="">— اختر —</option>{SOIL_TYPES.map((s) => <option key={s}>{s}</option>)}</select></F>
          <F label="ملوحة التربة EC dS/m · S3 (حاكم)"><input value={d.salinity} onChange={(e) => set("salinity", e.target.value)} placeholder="تحليل مخبري" inputMode="decimal" style={inp(false)} /></F>
          <div style={{ display: "flex", gap: 10 }}>
            <F label="حموضة pH · S4 (حاكم)" e={phWarn && phWarn.startsWith("pH") ? phWarn : ""}><input value={d.ph} onChange={(e) => set("ph", e.target.value)} placeholder="6.0–8.5" inputMode="decimal" style={inp(phWarn && phWarn.startsWith("pH"))} /></F>
            <F label="المادة العضوية OM %"><input value={d.om} onChange={(e) => set("om", e.target.value)} placeholder="1.2" inputMode="decimal" style={inp(false)} /></F>
          </div>
          {phWarn && !phWarn.startsWith("pH") && <div style={{ fontSize: 11, color: "#d4a017", marginTop: -10, marginBottom: 12 }}>{phWarn}</div>}
          <F label="ملوحة مياه الري EC dS/m · I3 (حاكم)"><input value={d.waterSalinity} onChange={(e) => set("waterSalinity", e.target.value)} placeholder="تحليل المياه" inputMode="decimal" style={inp(false)} /></F>
          <div style={hint}>💡 الاستشعار (NDVI/SI) يوجّه أين تأخذ العينة، والتحليل المخبري يحكم. لا توصية بلا قيمة حقيقية.</div>
        </div>)}

        {step === 5 && (<div>
          <H icon="💧" t="نظام الري" s="النوع يحدّد الحقول المطلوبة (كشف شرطي)" />
          <F label="نوع النظام" e={touched.irrigation && err.irrigation}><select value={d.irrigation} onChange={(e) => { set("irrigation", e.target.value); touch("irrigation"); }} style={inp(touched.irrigation && err.irrigation)}><option value="">— اختر —</option>{Object.entries(IRRIGATION).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}</select></F>
          {d.irrigation && IRRIGATION[d.irrigation].extra.includes("length") && <F label="طول المحوري (متر)"><input value={d.length} onChange={(e) => set("length", e.target.value)} placeholder="125" inputMode="decimal" style={inp(false)} /></F>}
          {d.irrigation && IRRIGATION[d.irrigation].extra.includes("controller") && <F label="نوع التحكّم"><select value={d.controller} onChange={(e) => set("controller", e.target.value)} style={inp(false)}><option value="">—</option><option>Valley</option><option>Lindsay</option><option>Reinke</option></select></F>}
          {d.irrigation && IRRIGATION[d.irrigation].extra.includes("flow") && <F label="معدل التدفّق (لتر/ثانية)"><input value={d.flow} onChange={(e) => set("flow", e.target.value)} placeholder="38" inputMode="decimal" style={inp(false)} /></F>}
          {d.irrigation && IRRIGATION[d.irrigation].extra.includes("runtime") && <F label="زمن الدورة الكاملة (ساعة)"><input value={d.runtime} onChange={(e) => set("runtime", e.target.value)} placeholder="9" inputMode="decimal" style={inp(false)} /></F>}
          {d.irrigation === "none" && <div style={hint}>زراعة بعلية — التوصيات تعتمد على الأمطار ورطوبة التربة.</div>}
        </div>)}

        {step === 6 && (<div>
          <H icon="✓" t="مراجعة وحفظ" s="تأكّد قبل الحفظ — وما الذي سيُفعّل" />
          <Row k="الحقل" v={d.name || "—"} /><Row k="الموقع" v={d.lat && d.lon ? `${d.lat}°N, ${d.lon}°E` : "—"} />
          <Row k="الموسم" v={d.season || "—"} /><Row k="المحصول" v={d.crop || "—"} />
          <Row k="نوع التربة" v={d.soilType || "—"} /><Row k="نظام الري" v={d.irrigation ? IRRIGATION[d.irrigation].label : "—"} />
          <div style={{ height: 1, background: "#2d4a37", margin: "12px 0" }} />
          <Row k="التحاليل الحاكمة" v={soilComplete ? "✅ كاملة" : "⚠️ ناقصة"} c={soilComplete ? "#5cbf6e" : "#d4a017"} />
          <div style={{ background: "#1a2b3a", borderRadius: 10, padding: 14, marginTop: 16, border: "1px solid #2d3f4a" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}><span style={{ fontSize: 13, color: "#cdddd2", fontWeight: 600 }}>توقّع الإنتاجية</span><span style={{ fontSize: 11, color: "#7fae8c" }}>قيد المعايرة</span></div>
            <div style={{ fontSize: 12, color: "#9cb8a3", marginTop: 6, lineHeight: 1.6 }}>الإنتاج المتوقّع يبقى <b style={{ color: "#4a90d4" }}>null</b> حتى معايرة ٥ مزارع/إقليم. بدلاً منه: أدخل <b>الحصاد الفعلي</b> نهاية الموسم — يُغذّي حلقة المعايرة (لا رقم وهمي).</div>
          </div>
          <div style={{ background: soilComplete ? "#1f3a2a" : "#3a1f1a", borderRadius: 10, padding: 14, marginTop: 12, fontSize: 13, color: "#e8eee9", borderRight: `3px solid ${soilComplete ? "#5cbf6e" : "#d4593a"}` }}>{soilComplete ? "🟢 بعد الحفظ: الحالة جاهز — التوصيات مُفعّلة" : "⚪ بعد الحفظ: الحالة BLOCKED — أدخل التحاليل لاحقاً للتفعيل"}</div>
        </div>)}

        <div style={{ display: "flex", gap: 10, marginTop: 22 }}>
          {step > 1 && <button onClick={() => setStep(step - 1)} style={btn2}>السابق</button>}
          {step < 6 ? <button onClick={() => ok && setStep(step + 1)} disabled={!ok} style={btn1(ok)}>التالي</button>
            : <button style={btn1(true)}>{soilComplete ? "حفظ وتفعيل التوصيات" : "حفظ (قيد الانتظار)"}</button>}
        </div>
      </div>
      <div style={{ maxWidth: 580, margin: "14px auto 0", textAlign: "center", fontSize: 11, color: "#7fae8c" }}>٦ خطوات · عربي أصيل · بوابة جودة → BLOCKED/جاهز · لا توقّع إنتاجية وهمي</div>
    </div>
  );
}

function H({ icon, t, s }: { icon: ReactNode; t: ReactNode; s: ReactNode }) { return <div style={{ marginBottom: 18 }}><div style={{ fontSize: 19, fontWeight: 800, color: "#fff" }}>{icon} {t}</div><div style={{ fontSize: 13, color: "#9cb8a3", marginTop: 4 }}>{s}</div></div>; }
function F({ label, e, children }: { label: string; e?: any; children: any }) { return <div style={{ marginBottom: 16, flex: 1 }}><label style={{ fontSize: 13, color: "#9cb8a3", display: "block", marginBottom: 6 }}>{label}</label>{children}{e && <div style={{ fontSize: 11, color: "#d4593a", marginTop: 4 }}>⚠ {e}</div>}</div>; }
function Row({ k, v, c = "#e8eee9" }: { k: ReactNode; v: ReactNode; c?: string }) { return <div style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", fontSize: 14 }}><span style={{ color: "#9cb8a3" }}>{k}</span><span style={{ color: c, fontWeight: 600 }}>{v}</span></div>; }
const inp = (e: unknown): CSSProperties => ({ width: "100%", padding: "12px 14px", borderRadius: 10, boxSizing: "border-box", background: "#0d1611", color: "#e8eee9", fontSize: 15, border: `1px solid ${e ? "#d4593a" : "#2d4a37"}`, outline: "none" });
const hint: CSSProperties = { fontSize: 12, color: "#7fae8c", background: "#0d1611", borderRadius: 8, padding: "10px 14px", marginTop: 8, lineHeight: 1.6 };
const btn1 = (on: boolean): CSSProperties => ({ flex: 2, padding: "14px", borderRadius: 12, border: "none", background: on ? "#5cbf6e" : "#2d4a37", color: on ? "#0d1611" : "#5a7263", fontSize: 15, fontWeight: 700, cursor: on ? "pointer" : "not-allowed", fontFamily: "inherit" });
const btn2: CSSProperties = { flex: 1, padding: "14px", borderRadius: 12, border: "1px solid #2d4a37", background: "transparent", color: "#9cb8a3", fontSize: 15, fontWeight: 600, cursor: "pointer", fontFamily: "inherit" };
