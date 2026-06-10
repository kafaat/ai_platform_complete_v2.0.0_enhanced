/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html','./src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        cairo:   ['Cairo','sans-serif'],
        tajawal: ['Tajawal','sans-serif'],
      },
      // نظام التصميم الموحّد — نفس قيم CSS variables الموجودة في index.css (:root)
      // وفئات الحالة، صارت tokens قابلة لإعادة الاستخدام (بدل inline متكرّر). لا اختراع.
      colors: {
        sahool: {
          green:        '#16a34a',  // --sahool-green
          'green-light':'#4ade80',  // --sahool-green-light
          'green-dark': '#15803d',  // --sahool-green-dark
          bg:           '#0f1117',  // --sahool-bg
          surface:      '#1e293b',  // --sahool-surface
          'surface-2':  '#172032',  // سطح ثانويّ (لوحة الطقس — قيمة مستعملة أصلاً)
          border:       '#334155',  // --sahool-border
          'border-focus':'#16a34a', // حدّ التركيز = الأخضر العلامي (focus ring)
          text:         '#e2e8f0',  // --sahool-text
          muted:        '#64748b',  // --sahool-muted
          accent:       '#38bdf8',  // --sahool-accent
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
