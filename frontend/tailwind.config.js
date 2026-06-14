/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html','./src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        cairo:   ['Cairo','sans-serif'],
        tajawal: ['Tajawal','sans-serif'],
      },
      // نظام التصميم الموحّد — ألوان sahool تُحلّ من CSS variables (ثلاثيّات RGB)
      // عبر rgb(var(--sahool-x) / <alpha-value>): تتبدّل مع السمة وتدعم مُعدّلات
      // الشفافية (مثل bg-sahool-surface/40). تُعرّف القيم في index.css لكل سمة.
      colors: {
        sahool: {
          green:        'rgb(var(--sahool-green) / <alpha-value>)',
          'green-light':'rgb(var(--sahool-green-light) / <alpha-value>)',
          'green-dark': 'rgb(var(--sahool-green-dark) / <alpha-value>)',
          bg:           'rgb(var(--sahool-bg) / <alpha-value>)',
          surface:      'rgb(var(--sahool-surface) / <alpha-value>)',
          'surface-2':  'rgb(var(--sahool-surface-2) / <alpha-value>)',
          border:       'rgb(var(--sahool-border) / <alpha-value>)',
          'border-focus':'rgb(var(--sahool-border-focus) / <alpha-value>)',
          text:         'rgb(var(--sahool-text) / <alpha-value>)',
          muted:        'rgb(var(--sahool-muted) / <alpha-value>)',
          accent:       'rgb(var(--sahool-accent) / <alpha-value>)',
        },
        // فئات الحالة (status-*) من index.css — نفس القيم، صارت ألوان Tailwind.
        status: {
          excellent: '#16a34a',
          good:      '#65a30d',
          fair:      '#ca8a04',
          poor:      '#f97316',
          critical:  '#dc2626',
        },
      },
    },
  },
  plugins: [],
};
