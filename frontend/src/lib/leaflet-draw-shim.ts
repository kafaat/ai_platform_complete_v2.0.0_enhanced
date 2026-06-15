// leaflet-draw-shim.ts — ظِلّ (shim) للمكوّن leaflet-draw.
//
// خلفيّة (عطل بناء): leaflet-draw مكتبة CommonJS ذات أثر جانبيّ فقط — تُسجّل
// L.Draw / L.Control.Draw / L.EditToolbar على فضاء أسماء leaflet ولا تُصدّر
// default. لكنّ مستهلكها react-leaflet-draw (ESM) يكتب:
//     import Draw from 'leaflet-draw';
// واستيراد default هذا يرفضه Vite 8 / rolldown بـ[MISSING_EXPORT] "default"،
// فيفشل `npm run build` (مع أنّ ربط Draw غير مُستخدَم إطلاقاً — الأثر الجانبيّ
// وحده هو المطلوب ليُتاح leaflet.Draw.Event داخل EditControl).
//
// الحلّ: نوجّه الـspecifier المجرّد 'leaflet-draw' (مطابقة تامّة فقط، عبر alias
// في vite.config) إلى هذا الملفّ، الذي يشغّل المكوّن لأثره الجانبيّ ثمّ يُصدّر
// فضاء أسماء leaflet (المُعزَّز) كـdefault فيتحقّق الاستيراد الصارم بلا كسر
// السلوك. مسارات leaflet-draw الفرعيّة (مثل dist/leaflet.draw.css) لا تتأثّر
// لأنّ الـalias مقيّد بـ/^leaflet-draw$/.
import 'leaflet-draw/dist/leaflet.draw.js';
import L from 'leaflet';

export default L;
