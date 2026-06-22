import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// هدف وكيل التطوير: بوّابة nginx الموحّدة افتراضيّاً (المنفذ 80 — المرجع القانونيّ في
// docker-compose.v9.yml). للتطوير المباشر بخدمات مفردة مكشوفة على منافذ المضيف، اضبط
// VITE_DEV_PROXY_TARGET (مثلاً http://localhost:8080).
const DEV_PROXY_TARGET = process.env.VITE_DEV_PROXY_TARGET || 'http://localhost';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: [
      { find: '@', replacement: path.resolve(__dirname, './src') },
      // leaflet-draw مكتبة CommonJS أثرها جانبيّ فقط (لا default). نوجّه
      // الـspecifier المجرّد فقط (/^leaflet-draw$/) إلى ظِلّ يشغّل الأثر الجانبيّ
      // ويُصدّر default — تستورده أداتنا maphub/DrawControl كأثر جانبيّ — دون
      // التأثير على المسارات الفرعيّة مثل leaflet-draw/dist/leaflet.draw.css.
      {
        // Exact match only: aliases the bare `leaflet-draw` import (no default
        // export) to a side-effect shim, without rewriting subpaths such as
        // `leaflet-draw/dist/leaflet.draw.css`.
        find: /^leaflet-draw$/,
        replacement: path.resolve(__dirname, './src/lib/leaflet-draw-shim.ts'),
      },
    ],
  },
  // ── وكيل التطوير: يوجّه كلّ نداءات API/Auth/WS إلى بوّابة nginx الموحّدة ──────
  // المرجع القانونيّ هو nginx (docker-compose.v9.yml، المنفذ 80 الوحيد المكشوف).
  // الإصدار السابق وجّه كلّ مسار إلى منفذ مضيف مستقلّ (8090/8091/8092…) محاكياً تجريد
  // nginx — لكنّ هذه المنافذ غير مكشوفة في v9، فيفشل `npm run dev` لبعض المسارات
  // (vegetation/indicators/weather/soil). الآن نوجّه /api و/auth و/ws إلى nginx بلا
  // rewrite — فهو يتكفّل بالتوجيه/التجريد الصحيح لكلّ خدمة. للخدمات المفردة: اضبط
  // VITE_DEV_PROXY_TARGET. التشغيل المُوصى به: افتح المنصّة عبر nginx مباشرةً.
  server: {
    proxy: {
      '/api':  { target: DEV_PROXY_TARGET, changeOrigin: true },
      '/auth': { target: DEV_PROXY_TARGET, changeOrigin: true },
      '/ws':   { target: DEV_PROXY_TARGET, changeOrigin: true, ws: true },
    },
  },
});
