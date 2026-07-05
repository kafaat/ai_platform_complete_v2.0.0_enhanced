import { useState } from "react";

// ════════════════════════════════════════════════════════════
// SAHOOL — مركز الإشعارات (Notification Center)
// يعرض الإشعارات الأربعة المبنية في core/data_completeness.py:
//   🟢 precise_ready  → توصياتك الدقيقة جاهزة
//   🧫 lab_results    → وصلت نتائج المعمل
//   💡 reminder       → أكمل بياناتك (قيمة الحقل التالي)
//   ✅ data_complete  → بياناتك مكتملة
// + إشعارات النظام (تنبيهات NDVI، طقس) من AlertSystem
//
// التصميم: داكن زراعي · RTL · إجراءات مباشرة · تمييز غير المقروء
// متّسق مع المعالج وبقية الواجهة (#14201a, أخضر #5cbf6e)
// ════════════════════════════════════════════════════════════

// لا نستخدم seed وهميّاً في مركز الإشعارات. ستُعبّأ هذه القائمة لاحقاً من
// websocket/toast store أو endpoint إشعارات فعلي؛ إلى أن يُربط المصدر الحيّ،
// تعرض الشاشة حالة فارغة صادقة بدل رسائل NDVI/طقس مخترعة.
type NotificationItem = {
  id: number;
  trigger: string;
  field: string;
  unread: boolean;
  time: string;
  title: string;
  body: string;
  action: string | null;
  accent: string;
};
const INITIAL_NOTIFICATIONS: NotificationItem[] = [];

const FILTERS = [
  { id: "all", label: "الكل" },
  { id: "unread", label: "غير المقروء" },
  { id: "data", label: "البيانات" },
  { id: "alerts", label: "التنبيهات" },
];

const DATA_TRIGGERS = ["precise_ready", "lab_results", "reminder", "data_complete"];
const ALERT_TRIGGERS = ["ndvi_alert", "weather"];

export default function NotificationCenter() {
  const [items, setItems] = useState<NotificationItem[]>(INITIAL_NOTIFICATIONS);
  const [filter, setFilter] = useState("all");

  const unreadCount = items.filter((i) => i.unread).length;

  const filtered = items.filter((i) => {
    if (filter === "unread") return i.unread;
    if (filter === "data") return DATA_TRIGGERS.includes(i.trigger);
    if (filter === "alerts") return ALERT_TRIGGERS.includes(i.trigger);
    return true;
  });

  const markRead = (id: number) => setItems((xs) => xs.map((i) => i.id === id ? { ...i, unread: false } : i));
  const markAllRead = () => setItems((xs) => xs.map((i) => ({ ...i, unread: false })));
  const dismiss = (id: number) => setItems((xs) => xs.filter((i) => i.id !== id));

  return (
    <div dir="rtl" style={{
      fontFamily: "'Noto Kufi Arabic', system-ui, sans-serif",
      background: "linear-gradient(160deg, #14201a 0%, #1c2b22 100%)",
      minHeight: "100vh", color: "#e8eee9", padding: 24,
    }}>
      <style>{`@import url('https://fonts.googleapis.com/css2?family=Noto+Kufi+Arabic:wght@400;600;800&display=swap');
        button { font-family: inherit; }`}</style>

      {/* الرأس */}
      <div style={{ maxWidth: 580, margin: "0 auto 20px", display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <div style={{ fontSize: 13, color: "#7fae8c", fontWeight: 600 }}>سهول · مزرعة السنيدار</div>
          <h1 style={{ fontSize: 24, fontWeight: 800, margin: "4px 0 0", color: "#fff", display: "flex", alignItems: "center", gap: 10 }}>
            الإشعارات
            {unreadCount > 0 && (
              <span style={{ fontSize: 13, background: "#5cbf6e", color: "#0d1611", borderRadius: 12, padding: "2px 10px", fontWeight: 700 }}>{unreadCount}</span>
            )}
          </h1>
        </div>
        {unreadCount > 0 && (
          <button onClick={markAllRead} style={{ background: "transparent", border: "1px solid #2d4a37", color: "#9cb8a3", borderRadius: 10, padding: "8px 14px", fontSize: 12, cursor: "pointer", fontWeight: 600 }}>
            تعليم الكل كمقروء
          </button>
        )}
      </div>

      {/* فلاتر */}
      <div style={{ maxWidth: 580, margin: "0 auto 16px", display: "flex", gap: 8 }}>
        {FILTERS.map((f) => (
          <button key={f.id} onClick={() => setFilter(f.id)} style={{
            flex: 1, padding: "10px", borderRadius: 10, cursor: "pointer", fontSize: 13, fontWeight: 600,
            border: filter === f.id ? "2px solid #5cbf6e" : "1px solid #2d4a37",
            background: filter === f.id ? "#1f3a2a" : "transparent",
            color: filter === f.id ? "#fff" : "#9cb8a3",
          }}>{f.label}</button>
        ))}
      </div>

      {/* القائمة */}
      <div style={{ maxWidth: 580, margin: "0 auto", display: "flex", flexDirection: "column", gap: 10 }}>
        {filtered.length === 0 ? (
          <div style={{ textAlign: "center", padding: "48px 24px", color: "#5a7263" }}>
            <div style={{ fontSize: 40, marginBottom: 12 }}>🌾</div>
            <div style={{ fontSize: 15 }}>لا توجد إشعارات هنا</div>
          </div>
        ) : filtered.map((n) => (
          <div key={n.id} onClick={() => n.unread && markRead(n.id)} style={{
            background: n.unread ? "#1c2e23" : "#18241d",
            borderRadius: 14, padding: "16px 18px",
            border: `1px solid ${n.unread ? "#2d4a37" : "#222f27"}`,
            borderRight: `3px solid ${n.accent}`,
            cursor: n.unread ? "pointer" : "default", position: "relative",
            transition: "background .2s",
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                  <span style={{ fontSize: 15, fontWeight: 700, color: "#fff" }}>{n.title}</span>
                  {n.unread && <span style={{ width: 8, height: 8, borderRadius: "50%", background: n.accent, flexShrink: 0 }} />}
                </div>
                <div style={{ fontSize: 13, color: "#cdddd2", lineHeight: 1.6 }}>{n.body}</div>
                <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 10 }}>
                  {n.action && (
                    <button onClick={(e) => { e.stopPropagation(); markRead(n.id); }} style={{
                      background: n.accent, color: "#0d1611", border: "none", borderRadius: 8,
                      padding: "6px 14px", fontSize: 12, fontWeight: 700, cursor: "pointer",
                    }}>{n.action} ←</button>
                  )}
                  <span style={{ fontSize: 11, color: "#5a7263" }}>{n.time} · {n.field}</span>
                </div>
              </div>
              <button onClick={(e) => { e.stopPropagation(); dismiss(n.id); }} style={{
                background: "transparent", border: "none", color: "#5a7263", fontSize: 16,
                cursor: "pointer", padding: 4, lineHeight: 1, flexShrink: 0,
              }}>✕</button>
            </div>
          </div>
        ))}
      </div>

      {/* تذييل */}
      <div style={{ maxWidth: 580, margin: "20px auto 0", textAlign: "center", fontSize: 11, color: "#7fae8c", lineHeight: 1.7 }}>
        لا تُعرض هنا إلا إشعارات وصلت فعلياً من النظام. لا توجد رسائل تجريبية أو مؤشرات مخترعة.
        <br />
        <span style={{ color: "#5a7263" }}>اربط مصدر الإشعارات الحي websocket/store لبدء عرض التنبيهات.</span>
      </div>
    </div>
  );
}
