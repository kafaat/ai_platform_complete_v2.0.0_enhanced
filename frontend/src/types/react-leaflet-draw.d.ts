// إعلان أنواع مبسّط لـreact-leaflet-draw (لا يشحن types رسميّة).
// نكتفي بـEditControl الذي نستخدمه؛ خصائصه مُمرَّرة إلى leaflet-draw.
declare module 'react-leaflet-draw' {
  import type { FC } from 'react';
  // أحداث leaflet-draw مُعرَّفة في @types/leaflet-draw (L.DrawEvents) — نستعملها
  // بدل any كي تُعرَف layer/layerType على المعالِجات.
  import type { DrawEvents } from 'leaflet';

  export interface EditControlProps {
    position?: 'topright' | 'topleft' | 'bottomright' | 'bottomleft';
    onCreated?: (e: DrawEvents.Created) => void;
    onEdited?: (e: DrawEvents.Edited) => void;
    onDeleted?: (e: DrawEvents.Deleted) => void;
    draw?: Record<string, unknown>;
    edit?: Record<string, unknown>;
  }

  export const EditControl: FC<EditControlProps>;
}
