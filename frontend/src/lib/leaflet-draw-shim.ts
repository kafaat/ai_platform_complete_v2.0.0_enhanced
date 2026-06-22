// leaflet-draw-shim.ts — ظِلّ (shim) للمكوّن leaflet-draw.
//
// خلفيّة: leaflet-draw مكتبة CommonJS ذات أثر جانبيّ فقط — تُسجّل
// L.Draw / L.Control.Draw / L.EditToolbar / L.Draw.Event على فضاء أسماء
// leaflet ولا تُصدّر default. أداتنا maphub/DrawControl تستوردها كأثر جانبيّ
//     import 'leaflet-draw';
// لتعزيز L.Control.Draw قبل إنشائها. نُبقي الـalias المجرّد (مطابقة تامّة فقط،
// عبر vite.config/vitest.config) موجّهاً إلى هذا الملفّ، الذي يشغّل المكوّن
// لأثره الجانبيّ ويُصدّر فضاء أسماء leaflet (المُعزَّز) كـdefault — فيبقى الحلّ
// متيناً تجاه استيراد default صارم لو أُضيف لاحقاً، دون كسر السلوك. مسارات
// leaflet-draw الفرعيّة (مثل dist/leaflet.draw.css) لا تتأثّر لأنّ الـalias
// مقيّد بـ/^leaflet-draw$/.
import 'leaflet-draw/dist/leaflet.draw.js';
import L from 'leaflet';

export default L;
