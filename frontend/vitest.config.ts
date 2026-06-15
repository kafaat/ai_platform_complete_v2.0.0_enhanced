// إعداد vitest الأدنى — بيئة jsdom للمكوّنات، وإعداد jest-dom للمُطابِقات.
// منفصل عن vite.config.ts كي لا يُحمَّل خادم التطوير/البناء إعدادات الاختبار.
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
  },
});
