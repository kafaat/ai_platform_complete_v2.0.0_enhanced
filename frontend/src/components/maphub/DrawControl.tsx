// ═══════════════════════════════════════════════════════════════
// SAHOOL — maphub/DrawControl.tsx
// أداة رسم Leaflet مبنيّة على leaflet-draw الخام (لا react-leaflet-draw).
// ───────────────────────────────────────────────────────────────
// الخلفيّة: react-leaflet-draw (v0.20) غير مُصان ويكسر تحت React 19 — كان
// مصدر عطل التشغيل «m.getState is not a function» بعد رسم حقل. هذا المكوّن
// بديل drop-in يطابق سطح خصائص EditControl تماماً (position/onCreated/
// onEdited/onDeleted/draw/edit)، لكنّه يستخدم L.Control.Draw مباشرةً عبر
// سياق react-leaflet v5 (useLeafletContext) فيتفادى الاعتماديّة المكسورة.
//
// السلوك المُحافَظ عليه 1:1 (مطابق لـEditControl):
//   • يُضاف داخل <FeatureGroup> — يقرأ مجموعتها (layerContainer) من السياق،
//     وهي نفسها التي تُربَط كـedit.featureGroup (هدف التحرير/الحذف).
//   • عند L.Draw.Event.CREATED: يُضاف الشكل المرسوم إلى المجموعة ثمّ يُستدعى
//     onCreated(e) — كي تقرأ المستهلِكات (recompute عبر eachLayer) الطبقة.
//   • L.Draw.Event.EDITED → onEdited(e)، L.Draw.Event.DELETED → onDeleted(e).
//   • draw/edit تُمرَّران كما هما (showArea:false يبقى محترَماً — يتفادى عطل
//     readableArea المعروف في leaflet-draw مع Leaflet 1.9).
//
// ملاحظة: نستورد 'leaflet-draw' كأثر جانبيّ (يُعزّز L.Control.Draw / L.Draw)
// و CSS الأداة — مطابقاً لِما كان EditControl يفعله ضمنيّاً.
// ═══════════════════════════════════════════════════════════════
import { useEffect, useRef } from 'react';
import { useLeafletContext } from '@react-leaflet/core';
import L from 'leaflet';
import 'leaflet-draw'; // أثر جانبيّ: يُعزّز L.Control.Draw / L.Draw / L.Draw.Event
import 'leaflet-draw/dist/leaflet.draw.css';

export type DrawPosition = 'topright' | 'topleft' | 'bottomright' | 'bottomleft';

export interface DrawControlProps {
  position?: DrawPosition;
  onCreated?: (e: L.DrawEvents.Created) => void;
  onEdited?: (e: L.DrawEvents.Edited) => void;
  onDeleted?: (e: L.DrawEvents.Deleted) => void;
  // خيارات أدوات الرسم (مضلّع/مستطيل/دائرة/خطّ…) — تُمرَّر حرفيّاً إلى leaflet-draw.
  draw?: L.Control.DrawConstructorOptions['draw'];
  // خيارات شريط التحرير ({ edit, remove }) — featureGroup يُضاف داخليّاً من السياق.
  edit?: Omit<NonNullable<L.Control.DrawConstructorOptions['edit']>, 'featureGroup'>;
}

// مجموعة الطبقات هي L.FeatureGroup الموفَّرة من <FeatureGroup> الأب عبر السياق.
function isFeatureGroup(x: unknown): x is L.FeatureGroup {
  return x instanceof L.FeatureGroup;
}

export default function DrawControl({
  position = 'topright',
  onCreated,
  onEdited,
  onDeleted,
  draw,
  edit,
}: DrawControlProps) {
  const context = useLeafletContext();
  // نُبقي أحدث الـcallbacks في مراجع كي لا يُعاد إنشاء الأداة عند كلّ تصيير
  // (مطابقةً لاستقرار EditControl — الأداة تُنشَأ مرّة وتُزال عند التفكيك).
  const onCreatedRef = useRef(onCreated);
  const onEditedRef = useRef(onEdited);
  const onDeletedRef = useRef(onDeleted);
  onCreatedRef.current = onCreated;
  onEditedRef.current = onEdited;
  onDeletedRef.current = onDeleted;

  // ثبات إعدادات الرسم/التحرير عبر التصيير (JSON يكفي — قيم تسلسليّة بسيطة).
  const drawKey = JSON.stringify(draw ?? null);
  const editKey = JSON.stringify(edit ?? null);

  useEffect(() => {
    const map = context.map;
    const container = context.layerContainer;
    // المجموعة المُستهدَفة للتحرير/الحذف = مجموعة <FeatureGroup> الأب.
    const featureGroup = isFeatureGroup(container) ? container : undefined;
    if (!map || !featureGroup) return;

    const drawControl = new L.Control.Draw({
      position,
      draw: draw ?? {},
      // featureGroup مطلوب دائماً لشريط التحرير؛ نمرّر خيارات edit/remove كما هي.
      edit: { featureGroup, ...(edit ?? {}) },
    });
    map.addControl(drawControl);

    const handleCreated = (e: L.LeafletEvent) => {
      const evt = e as unknown as L.DrawEvents.Created;
      // مطابقة سلوك EditControl: الشكل المرسوم يُضاف للمجموعة قبل ردّ النداء،
      // كي تقرأه المستهلِكات عبر group.eachLayer (القياس/المناطق).
      featureGroup.addLayer(evt.layer);
      onCreatedRef.current?.(evt);
    };
    const handleEdited = (e: L.LeafletEvent) => {
      onEditedRef.current?.(e as unknown as L.DrawEvents.Edited);
    };
    const handleDeleted = (e: L.LeafletEvent) => {
      onDeletedRef.current?.(e as unknown as L.DrawEvents.Deleted);
    };

    map.on(L.Draw.Event.CREATED, handleCreated);
    map.on(L.Draw.Event.EDITED, handleEdited);
    map.on(L.Draw.Event.DELETED, handleDeleted);

    return () => {
      map.off(L.Draw.Event.CREATED, handleCreated);
      map.off(L.Draw.Event.EDITED, handleEdited);
      map.off(L.Draw.Event.DELETED, handleDeleted);
      map.removeControl(drawControl);
    };
    // إعادة الإنشاء فقط عند تغيّر الخريطة/المجموعة أو إعدادات الرسم/التحرير/الموضع.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [context.map, context.layerContainer, position, drawKey, editKey]);

  return null;
}
