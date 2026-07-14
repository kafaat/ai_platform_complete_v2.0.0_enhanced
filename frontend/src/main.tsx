import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import './index.css';
import { useAuthStore } from './hooks/useAuth';
import { useFieldContextStore } from './hooks/useFieldContext';
import { resetDuckDB } from './services/duckdb';
import { wsService } from './services/websocket';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { refetchOnWindowFocus: false, retry: 2, staleTime: 30000 },
  },
});

// عزل كاش المستأجِر (F5-01/F5-05): أيّ تغيّر في هويّة المستأجِر (تسجيل دخول، تبديل
// مستأجِر، خروج/401) يُفرّغ كامل كاش React Query ويُصفّر سياق الحقل المُثبَّت ومثيل
// DuckDB المُتشارَك — فلا تبقى بيانات مستأجِرٍ سابق قابلةً للقراءة/التصدير حتى لو
// تصادفت معرّفات الحقول. عند فقد الهويّة (خروج) نقطع WebSocket أيضاً.
let _prevTenant = useAuthStore.getState().tenantId;
useAuthStore.subscribe((state) => {
  if (state.tenantId === _prevTenant) return;
  _prevTenant = state.tenantId;
  queryClient.clear();
  useFieldContextStore.getState().clearSelectedField();
  void resetDuckDB();
  if (!state.tenantId) wsService.disconnect();
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      {/* BrowserRouter يلفّ التطبيق كلّه — يُمكّن الروابط العميقة وزرّ الرجوع. */}
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
