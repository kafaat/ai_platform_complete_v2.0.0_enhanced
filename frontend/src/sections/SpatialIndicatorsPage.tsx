import { useState, useMemo } from "react";

// ════════════════════════════════════════════════════════════
// SAHOOL — صفحة المؤشرات المكانية (Spatial Indicators View)
// تعرض مخرجات core/spatial/indicators.py:
//   • شبكة NDVI فوق الحقل (بلاطات ملوّنة لكل بكسل)
//   • كشف مناطق الاهتمام (انحراف معياري عن متوسط الحقل)
//   • إحداثية كل منطقة + تفسير + ربط بمعرفة المزارع
//   • شريط زمني (timeline) للمقارنة
// المنطق يطابق الـ backend تماماً (نفس عتبة الانحراف المعياري).
// ════════════════════════════════════════════════════════════

const FIELD_BBOX = { minLon: 45.300, minLat: 16.150, maxLon: 45.307, maxLat: 16.157 };
const GRID = 24; // 24×24 بكسل (محاكاة دقة Sentinel للمحوري)

// مؤشرات قابلة للعرض المكاني (تطابق SpatialIndex في الـ backend)
const INDICES = {
  ndvi: { name: "NDVI", label: "صحة الغطاء النباتي", lowIsProblem: true, healthy: 0.7 },
  ndmi: { name: "NDMI", label: "رطوبة المحتوى", lowIsProblem: true, healthy: 0.5 },
  salinity: { name: "SI", label: "مؤشر الملوحة", lowIsProblem: false, healthy: 0.2 },
};

// توليد شبكة محاكاة (الحقل صحي + بقعة شمالية ضعيفة — كمعرفة المزارع)
function genGrid(indexKey, seed) {
  const idx = INDICES[indexKey];
  const base = idx.healthy;
  const g = [];
  let s = seed;
  const rand = () => { s = (s * 9301 + 49297) % 233280; return s / 233280; };
  for (let r = 0; r < GRID; r++) {
    const row = [];
    for (let c = 0; c < GRID; c++) {
      let v;
      // بقعة اهتمام في الشمال الغربي (صفوف 2-7، أعمدة 2-8)
      const inPatch = r >= 2 && r <= 7 && c >= 2 && c <= 8;
      if (idx.lowIsProblem) {
        v = inPatch ? 0.30 + rand() * 0.06 : base + (rand() - 0.5) * 0.10;
      } else {
        v = inPatch ? 0.55 + rand() * 0.08 : base + (rand() - 0.5) * 0.08;
      }
      row.push(Math.max(0, Math.min(1, v)));
    }
    g.push(row);
  }
  return g;
}

// إحصاء الحقل
function stats(grid) {
  const flat = grid.flat();
  const mean = flat.reduce((a, b) => a + b, 0) / flat.length;
  const sd = Math.sqrt(flat.reduce((a, b) => a + (b - mean) ** 2, 0) / flat.length);
  return { mean, sd };
}

// كشف مناطق الاهتمام (يطابق detect_zones_of_interest في الـ backend)
function detectZones(grid, indexKey, thresholdStd = 1.0, minCluster = 3) {
  const idx = INDICES[indexKey];
  const { mean, sd } = stats(grid);
  if (sd === 0) return [];
  const mask = grid.map(row => row.map(v =>
    idx.lowIsProblem ? v < mean - thresholdStd * sd : v > mean + thresholdStd * sd
  ));
  // connected components (BFS)
  const seen = new Set();
  const clusters = [];
  for (let r = 0; r < GRID; r++) for (let c = 0; c < GRID; c++) {
    if (mask[r][c] && !seen.has(`${r},${c}`)) {
      const stack = [[r, c]], comp = [];
      while (stack.length) {
        const popped = stack.pop();
        if (!popped) break;
        const [cr, cc] = popped;
        const k = `${cr},${cc}`;
        if (seen.has(k) || cr < 0 || cr >= GRID || cc < 0 || cc >= GRID || !mask[cr][cc]) continue;
        seen.add(k); comp.push([cr, cc]);
        stack.push([cr + 1, cc], [cr - 1, cc], [cr, cc + 1], [cr, cc - 1]);
      }
      if (comp.length >= minCluster) clusters.push(comp);
    }
  }
  return clusters.map(comp => {
    const rows = comp.map(p => p[0]), cols = comp.map(p => p[1]);
    const cr = rows.reduce((a, b) => a + b, 0) / rows.length;
    const cc = cols.reduce((a, b) => a + b, 0) / cols.length;
    const lon = FIELD_BBOX.minLon + (cc + 0.5) / GRID * (FIELD_BBOX.maxLon - FIELD_BBOX.minLon);
    const lat = FIELD_BBOX.maxLat - (cr + 0.5) / GRID * (FIELD_BBOX.maxLat - FIELD_BBOX.minLat);
    const vals = comp.map(([r, c]) => grid[r][c]);
    const mv = vals.reduce((a, b) => a + b, 0) / vals.length;
    const dev = Math.abs(mv - mean) / sd;
    const sev = dev >= 2 ? "high" : dev >= 1.5 ? "medium" : "low";
    return {
      lon: lon.toFixed(5), lat: lat.toFixed(5),
      pixels: comp.length, meanVal: mv.toFixed(3), fieldMean: mean.toFixed(3),
      severity: sev, comp,
    };
  }).sort((a, b) => b.pixels - a.pixels);
}

// لون البكسل حسب القيمة والمؤشر
function pixelColor(v, indexKey) {
  const idx = INDICES[indexKey];
  let t = idx.lowIsProblem ? v : 1 - v; // t: 1=صحي, 0=مشكلة
  t = Math.max(0, Math.min(1, t));
  // تدرّج من أحمر (مشكلة) لأخضر داكن (صحي) — ألوان زراعية
  if (t > 0.75) return "#1a7a3c";
  if (t > 0.55) return "#5c9a2e";
  if (t > 0.4) return "#b8920f";
  if (t > 0.25) return "#c75416";
  return "#a32014";
}

const SEV_AR = { high: "🔴 شديد", medium: "🟡 متوسط", low: "🟢 طفيف" };
const TIMELINE = [
  { date: "2026-05-22", cloud: 8, q: "صافٍ", sat: "S2" },
  { date: "2026-05-17", cloud: 35, q: "دمج S1+S2", sat: "S1+S2" },
  { date: "2026-05-12", cloud: 72, q: "رادار", sat: "S1" },
  { date: "2026-05-07", cloud: 5, q: "صافٍ", sat: "S2" },
];

export default function SpatialView() {
  const [indexKey, setIndexKey] = useState("ndvi");
  const [tIdx, setTIdx] = useState(0);
  const [selectedZone, setSelectedZone] = useState(null);

  const grid = useMemo(() => genGrid(indexKey, 42 + tIdx * 7), [indexKey, tIdx]);
  const zones = useMemo(() => detectZones(grid, indexKey), [grid, indexKey]);
  const fieldStats = useMemo(() => stats(grid), [grid]);
  const idx = INDICES[indexKey];

  const interp = (k) => ({
    ndvi: "غطاء نباتي ضعيف — فرضيات: ملوحة، نقص ري، نقص تغذية، أو إصابة. يحتاج تحقّقاً ميدانياً.",
    ndmi: "رطوبة منخفضة — منطقة جافة محتملة. راجع توزيع الري.",
    salinity: "مؤشر ملوحة مرتفع — بقعة مالحة محتملة. خذ عينة تربة (S3).",
  }[k]);

  const zoneCells = new Set();
  zones.forEach((z, zi) => z.comp.forEach(([r, c]) => zoneCells.add(`${r},${c}`)));

  return (
    <div dir="rtl" style={{
      fontFamily: "'Noto Kufi Arabic', system-ui, sans-serif",
      background: "linear-gradient(160deg, #14201a 0%, #1c2b22 100%)",
      minHeight: "100vh", color: "#e8eee9", padding: "24px",
    }}>
      <style>{`@import url('https://fonts.googleapis.com/css2?family=Noto+Kufi+Arabic:wght@400;600;800&display=swap');`}</style>

      {/* العنوان */}
      <div style={{ marginBottom: 20, borderBottom: "2px solid #2d4a37", paddingBottom: 16 }}>
        <div style={{ fontSize: 13, color: "#7fae8c", letterSpacing: 1, fontWeight: 600 }}>
          سهول · المؤشرات المكانية
        </div>
        <h1 style={{ fontSize: 26, fontWeight: 800, margin: "4px 0 0", color: "#fff" }}>
          الحقل المحدّد <span style={{ fontSize: 14, color: "#7fae8c", fontWeight: 400 }}>(المؤشرات المكانية)</span>
        </h1>
      </div>

      {/* تحذير صدق: هذه الصفحة تعرض بيانات محاكاة توضيحيّة، لا قراءات قمر حقيقيّة */}
      <div style={{
        marginBottom: 16, padding: "12px 16px", borderRadius: 10,
        background: "#3a2e14", border: "1px solid #7a5a1a", color: "#f0d68a",
        fontSize: 13, fontWeight: 600,
      }}>
        ⚠️ عرض توضيحي: الشبكة أدناه بيانات محاكاة لتوضيح الواجهة فقط، وليست
        قراءات Sentinel فعليّة لحقلك. لا تتّخذ قرارات ريّ أو تسميد بناءً عليها.
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 340px", gap: 20 }}>
        {/* العمود الأيمن: الخريطة */}
        <div>
          {/* اختيار المؤشر */}
          <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
            {Object.entries(INDICES).map(([k, v]) => (
              <button key={k} onClick={() => { setIndexKey(k); setSelectedZone(null); }}
                style={{
                  flex: 1, padding: "10px 8px", borderRadius: 10, cursor: "pointer",
                  border: indexKey === k ? "2px solid #5cbf6e" : "1px solid #2d4a37",
                  background: indexKey === k ? "#1f3a2a" : "transparent",
                  color: indexKey === k ? "#fff" : "#9cb8a3", fontWeight: 600,
                  fontFamily: "inherit", transition: "all .2s",
                }}>
                <div style={{ fontSize: 15 }}>{v.name}</div>
                <div style={{ fontSize: 10, opacity: .7 }}>{v.label}</div>
              </button>
            ))}
          </div>

          {/* الشبكة فوق الخريطة */}
          <div style={{
            position: "relative", borderRadius: 14, overflow: "hidden",
            border: "1px solid #2d4a37", background: "#0d1611",
            boxShadow: "0 8px 32px rgba(0,0,0,.4)",
          }}>
            <div style={{
              display: "grid", gridTemplateColumns: `repeat(${GRID}, 1fr)`,
              gap: 1, padding: 8, aspectRatio: "1",
            }}>
              {grid.map((row, r) => row.map((v, c) => {
                const inZone = zoneCells.has(`${r},${c}`);
                const inSel = selectedZone && selectedZone.comp.some(([zr, zc]) => zr === r && zc === c);
                return (
                  <div key={`${r}-${c}`} title={`${idx.name}=${v.toFixed(2)}`}
                    style={{
                      background: pixelColor(v, indexKey), borderRadius: 2,
                      outline: inSel ? "2px solid #fff" : inZone ? "1px solid rgba(255,255,255,.5)" : "none",
                      outlineOffset: -1, transition: "outline .2s",
                    }} />
                );
              }))}
            </div>
            {/* مؤشر الاتجاه */}
            <div style={{
              position: "absolute", top: 12, right: 12, background: "rgba(13,22,17,.85)",
              borderRadius: 8, padding: "4px 10px", fontSize: 11, color: "#7fae8c",
            }}>ش ↑ · {FIELD_BBOX.maxLat.toFixed(3)}°N</div>
          </div>

          {/* مفتاح الألوان */}
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 12, fontSize: 12, color: "#9cb8a3" }}>
            <span>مشكلة</span>
            <div style={{ flex: 1, height: 10, borderRadius: 5, background: "linear-gradient(90deg,#a32014,#c75416,#b8920f,#5c9a2e,#1a7a3c)" }} />
            <span>صحي</span>
          </div>

          {/* الشريط الزمني */}
          <div style={{ marginTop: 18 }}>
            <div style={{ fontSize: 12, color: "#7fae8c", marginBottom: 8, fontWeight: 600 }}>الشريط الزمني · مقارنة</div>
            <div style={{ display: "flex", gap: 8 }}>
              {TIMELINE.map((t, i) => (
                <button key={i} onClick={() => setTIdx(i)}
                  style={{
                    flex: 1, padding: "8px 6px", borderRadius: 8, cursor: "pointer",
                    border: tIdx === i ? "2px solid #5cbf6e" : "1px solid #2d4a37",
                    background: tIdx === i ? "#1f3a2a" : "transparent",
                    fontFamily: "inherit",
                  }}>
                  <div style={{ fontSize: 11, color: "#e8eee9", fontWeight: 600 }}>{t.date.slice(5)}</div>
                  <div style={{ fontSize: 9, color: t.cloud > 20 ? "#d4a017" : "#7fae8c", marginTop: 2 }}>
                    ☁ {t.cloud}% · {t.q}
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* العمود الأيسر: مناطق الاهتمام */}
        <div>
          {/* إحصاء الحقل */}
          <div style={{
            background: "#1a2b21", borderRadius: 12, padding: 16, marginBottom: 14,
            border: "1px solid #2d4a37",
          }}>
            <div style={{ fontSize: 12, color: "#7fae8c", fontWeight: 600 }}>متوسط الحقل · {idx.name}</div>
            <div style={{ fontSize: 32, fontWeight: 800, color: "#fff", margin: "4px 0" }}>
              {fieldStats.mean.toFixed(2)}
            </div>
            <div style={{ fontSize: 11, color: "#9cb8a3" }}>
              انحراف معياري {fieldStats.sd.toFixed(3)} · {GRID}×{GRID} بكسل
            </div>
          </div>

          {/* مناطق الاهتمام */}
          <div style={{ fontSize: 13, color: "#fff", fontWeight: 700, marginBottom: 10 }}>
            مناطق الاهتمام ({zones.length})
          </div>
          {zones.length === 0 && (
            <div style={{ color: "#7fae8c", fontSize: 13, padding: 16, textAlign: "center" }}>
              ✓ لا مناطق شاذّة — الحقل متجانس
            </div>
          )}
          {zones.map((z, i) => (
            <div key={i} onClick={() => setSelectedZone(selectedZone === z ? null : z)}
              style={{
                background: selectedZone === z ? "#243a2c" : "#1a2b21",
                borderRadius: 12, padding: 14, marginBottom: 10, cursor: "pointer",
                border: selectedZone === z ? "2px solid #5cbf6e" : "1px solid #2d4a37",
                transition: "all .2s",
              }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 14, fontWeight: 700, color: "#fff" }}>{SEV_AR[z.severity]}</span>
                <span style={{ fontSize: 11, color: "#9cb8a3" }}>{z.pixels} بكسل</span>
              </div>
              <div style={{ fontSize: 12, color: "#9cb8a3", margin: "8px 0" }}>
                {idx.name} = <b style={{ color: "#fff" }}>{z.meanVal}</b> · متوسط الحقل {z.fieldMean}
              </div>
              <div style={{
                fontSize: 12, color: "#5cbf6e", fontFamily: "monospace",
                background: "#0d1611", borderRadius: 6, padding: "6px 10px", marginBottom: 8,
              }}>
                📍 {z.lat}°N, {z.lon}°E
              </div>
              {selectedZone === z && (
                <div style={{ fontSize: 12, color: "#cdddd2", lineHeight: 1.7, marginTop: 8 }}>
                  <div style={{ marginBottom: 8 }}>{interp(indexKey)}</div>
                  {indexKey === "ndvi" && (
                    <div style={{
                      background: "#2a3d1f", borderRadius: 8, padding: "8px 12px",
                      borderRight: "3px solid #5cbf6e", fontSize: 11,
                    }}>
                      💡 معرفة المزارع تؤكّد: «الطرف الشمالي ضعيف الإنتاج دائماً»
                    </div>
                  )}
                  <div style={{
                    marginTop: 8, background: "#3a2a1a", borderRadius: 8,
                    padding: "8px 12px", borderRight: "3px solid #d4a017", fontSize: 11,
                  }}>
                    🎯 يوجّه أخذ عينة تربة (S3) هنا — يسدّ فجوة البيانات الناقصة
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* تذييل: مبدأ الصدق */}
      <div style={{
        marginTop: 20, padding: 14, borderRadius: 10, background: "#0d1611",
        border: "1px dashed #2d4a37", fontSize: 11, color: "#7fae8c", textAlign: "center",
      }}>
        الاستشعار يوجّه · المختبر يحكم — مؤشر القمر استرشادي (±0.05–0.10)، يكشف البقعة المشبوهة،
        والتحليل المخبري (S3) يؤكّد ويقيس. لا توصية بلا بيانات حقيقية.
      </div>
    </div>
  );
}
