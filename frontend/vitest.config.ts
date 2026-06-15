// إعداد vitest الأدنى — بيئة jsdom للمكوّنات، وإعداد jest-dom للمُطابِقات.
// منفصل عن vite.config.ts كي لا يُحمَّل خادم التطوير/البناء إعدادات الاختبار.
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    // نفس alias الخاصّ بـvite.config.ts: نُبقي ظِلّ leaflet-draw فعّالاً في الاختبار
    // أيضاً (إن استورده اختبار transitively) فلا يتعارض حلّ الوحدات بين البناء والاختبار.
    alias: [
      { find: '@', replacement: path.resolve(__dirname, './src') },
      {
        find: /^leaflet-draw$/,
        replacement: path.resolve(__dirname, './src/lib/leaflet-draw-shim.ts'),
      },
    ],
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
  },
});
