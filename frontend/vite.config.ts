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
  // DuckDB-WASM (ورشة SQL): يُستضاف ذاتيّاً عبر استيراد ?url ويُحمَّل كسولاً في chunk منفصل.
  // exclude يمنع التحزيم المسبق (يستعمل محمّل worker خاصّاً)؛ worker.format='es' لدعم
  // الـworker في المتصفّح؛ ورفع حدّ تحذير الحجم لأنّ حزمة WASM ~2.5MB (كسولة، خارج الرئيسة).
  optimizeDeps: {
    exclude: ['@duckdb/duckdb-wasm'],
  },
  worker: {
    format: 'es',
  },
  build: {
    // Keep the warning meaningful. DuckDB workers are emitted separately and the
    // heavy GIS routes are lazy; application/vendor chunks should stay below 1 MiB.
    chunkSizeWarningLimit: 1050,
    rollupOptions: {
      output: {
        // Stable framework/domain boundaries improve caching and keep the entry
        // chunk from absorbing libraries used by many lazy screens.
        manualChunks(id) {
          if (!id.includes('/node_modules/')) return undefined;
          const groups: Array<[string, string[]]> = [
            ['vendor-react', ['react', 'react-dom', 'react-router-dom', '@tanstack/react-query', 'zustand']],
            ['vendor-ui', ['lucide-react', 'framer-motion', 'cmdk']],
            ['vendor-charts', ['recharts', 'd3-']],
            // NOTE: the Leaflet ecosystem is deliberately NOT manually chunked. Its
            // plugins (leaflet-draw, @geoman-io/leaflet-geoman-free) are UMD modules
            // that reference the bare global `L` at module-load; forcing them into a
            // standalone vendor chunk breaks that interop and throws "L is not defined"
            // (blank app). Leave leaflet to the automatic shared-chunk splitting, which
            // keeps the interop intact.
            ['vendor-maplibre', ['maplibre-gl']],
            ['vendor-terra-draw', ['terra-draw', 'terra-draw-maplibre-gl-adapter']],
            ['vendor-turf', ['@turf/']],
          ];
          for (const [chunk, packages] of groups) {
            if (packages.some((pkg) => id.includes(`/node_modules/${pkg}`))) return chunk;
          }
          return undefined;
        },
      },
    },
  },
});
