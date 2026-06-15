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
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
});
