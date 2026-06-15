// ═══════════════════════════════════════════════════════════════
// SAHOOL — lib/leafletSetup.ts
// تهيئة Leaflet جانبيّة (side-effect) تُستورَد فقط من مكوّنات الخرائط
// (FieldIndicatorMap / AddFieldWithMap) — لا من main.tsx — كي يبقى Leaflet
// ضمن الحزم المُقسَّمة بالمسار (lazy) فلا يُثقِل التحميل الأوّل لمن لا يفتح
// صفحات الخرائط (مراجعة Copilot).
//
// الحاسم: CSS الأساسيّ لـLeaflet — بدونه تُصيَّر الخريطة كصندوق رماديّ مكسور
// (البلاطات تُحمَّل لكن بلا تموضع/أبعاد) ⇒ كان السبب في «لا تظهر أيّ خريطة».
// ═══════════════════════════════════════════════════════════════
import 'leaflet/dist/leaflet.css';
import 'leaflet-draw/dist/leaflet.draw.css';

import L from 'leaflet';
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png';
import markerIcon from 'leaflet/dist/images/marker-icon.png';
import markerShadow from 'leaflet/dist/images/marker-shadow.png';

// إصلاح أيقونات Leaflet الافتراضيّة مع Vite (وإلّا علامات الدبابيس مكسورة 404).
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
});
