import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
// CSS الأساسيّ لـLeaflet — بدونه تُصيَّر كلّ الخرائط كصندوق رماديّ مكسور (البلاطات
// تُحمَّل لكن بلا تموضع/أبعاد). كان مفقوداً ⇒ «لا تظهر أيّ خريطة». يُستورَد عالميّاً
// مرّة واحدة هنا قبل index.css (كي تبقى تخصيصاتنا فوقه). + CSS أداة الرسم.
import 'leaflet/dist/leaflet.css';
import 'leaflet-draw/dist/leaflet.draw.css';
// إصلاح أيقونات Leaflet الافتراضيّة مع Vite (وإلّا علامات الدبابيس مكسورة 404).
import L from 'leaflet';
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png';
import markerIcon from 'leaflet/dist/images/marker-icon.png';
import markerShadow from 'leaflet/dist/images/marker-shadow.png';
import App from './App';
import './index.css';

L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
});

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { refetchOnWindowFocus: false, retry: 2, staleTime: 30000 },
  },
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>
);
