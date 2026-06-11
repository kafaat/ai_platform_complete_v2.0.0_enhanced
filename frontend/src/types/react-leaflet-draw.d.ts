// إعلان أنواع مبسّط لـreact-leaflet-draw (لا يشحن types رسميّة).
// نكتفي بـEditControl الذي نستخدمه؛ خصائصه مُمرَّرة إلى leaflet-draw.
declare module 'react-leaflet-draw' {
  import type { FC } from 'react';

  export interface EditControlProps {
    position?: 'topright' | 'topleft' | 'bottomright' | 'bottomleft';
    onCreated?: (e: any) => void;
    onEdited?: (e: any) => void;
    onDeleted?: (e: any) => void;
    draw?: Record<string, any>;
    edit?: Record<string, any>;
  }

  export const EditControl: FC<EditControlProps>;
}
