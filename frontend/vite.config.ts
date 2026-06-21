import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: [
      { find: '@', replacement: path.resolve(__dirname, './src') },
      // عطل بناء Vite: react-leaflet-draw يستورد default من leaflet-draw الذي
      // لا يُصدّر default (أثر جانبيّ فقط). نوجّه الـspecifier المجرّد فقط
      // (/^leaflet-draw$/) إلى ظِلّ يشغّل الأثر الجانبيّ ويُصدّر default، دون
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
  // ── وكيل التطوير: يُحاكي توجيه nginx :80 (المرجع القانونيّ) ──────────────
  // في وضع gateway (الافتراضيّ) تنادي الواجهةُ مساراتٍ نسبيّةً؛ هذا الوكيل يجعل
  // `vite dev` يعمل بنفس قواعد nginx (nginx/nginx.fixed.conf): يُجرّد البادئة حيث
  // يُجرّدها nginx (raster/vegetation/weather)، ويُبقيها لـ/api/v1 و/auth.
  // المنافذ من docker-compose.fixed.yml/.env (platform 8000، auth 8120، raster 8001).
  // ملاحظة: vegetation/indicators/weather داخليّاً على 8000 — للوكيل وجّهناها إلى
  // منافذ مضيف محتملة (8090/8091/8092)؛ إن لم تُنشَر هذه المنافذ شغّل dev خلف
  // nginx بدل وكيل vite، أو اضبط VITE_API_MODE=dev مع المنافذ المباشرة.
  server: {
    proxy: {
      // المنطق الأساسيّ — يُبقي /api/v1 (nginx لا يُجرّده).
      '/api/v1':          { target: 'http://localhost:8000', changeOrigin: true },
      // المصادقة — يُبقي /auth (nginx لا يُجرّده؛ يطبّع المزدوج /auth/auth/).
      '/auth':            { target: 'http://localhost:8120', changeOrigin: true },
      // الراستر — nginx يُجرّد /api/raster.
      '/api/raster':      { target: 'http://localhost:8001', changeOrigin: true, rewrite: (p) => p.replace(/^\/api\/raster/, '') },
      // الغطاء النباتيّ — nginx يُجرّد /api/vegetation.
      '/api/vegetation':  { target: 'http://localhost:8090', changeOrigin: true, rewrite: (p) => p.replace(/^\/api\/vegetation/, '') },
      // المؤشّرات — nginx يُعيد الكتابة إلى /api/v1/indicators/ (نُحاكيها هنا).
      '/api/indicators':  { target: 'http://localhost:8091', changeOrigin: true, rewrite: (p) => p.replace(/^\/api\/indicators/, '/api/v1/indicators') },
      // الطقس — nginx يُجرّد /api/weather.
      '/api/weather':     { target: 'http://localhost:8092', changeOrigin: true, rewrite: (p) => p.replace(/^\/api\/weather/, '') },
      // المستشار — nginx يُحوّل /api/agent/ إلى /agent/ في خدمة المُشرف.
      '/api/agent':       { target: 'http://localhost:8000', changeOrigin: true, rewrite: (p) => p.replace(/^\/api\/agent/, '/agent') },
      // حواجز الأمان — nginx يُجرّد /api/guardrails.
      '/api/guardrails':  { target: 'http://localhost:8000', changeOrigin: true, rewrite: (p) => p.replace(/^\/api\/guardrails/, '') },
      // WebSocket الإشعارات — nginx /ws/ → خدمة الإشعارات :8123.
      '/ws':              { target: 'http://localhost:8123', changeOrigin: true, ws: true },
    },
  },
});
