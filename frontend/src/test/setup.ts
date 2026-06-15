// إعداد بيئة الاختبار — يُحمّل مُطابِقات jest-dom (toBeInTheDocument …)
// ويُنظّف شجرة DOM بعد كلّ اختبار لتفادي تسرّب الحالة بين الاختبارات.
import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

afterEach(() => {
  cleanup();
});
