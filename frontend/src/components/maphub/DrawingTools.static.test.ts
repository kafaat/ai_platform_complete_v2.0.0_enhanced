// حارس ساكن لأدوات الرسم/القياس + حصرها المتبادل مع الدبابيس — لا DOM، يعمل بثبات.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const root = process.cwd();
const drawControl = readFileSync(join(root, 'src/components/maphub/DrawControl.tsx'), 'utf8');
const hubMap = readFileSync(join(root, 'src/components/maphub/HubMap.tsx'), 'utf8');
const mapHub = readFileSync(join(root, 'src/sections/MapHub.tsx'), 'utf8');

describe('Drawing tools — leaflet-draw adapter (React 19 safe)', () => {
  it('does not import the unmaintained react-leaflet-draw (uses raw leaflet-draw)', () => {
    // يُذكَر react-leaflet-draw في تعليق يشرح سبب تفاديه؛ الحاسم ألّا يُستورَد فعليّاً.
    expect(drawControl).not.toMatch(/from ['"]react-leaflet-draw['"]/);
    expect(drawControl).toContain("import 'leaflet-draw'");
    expect(drawControl).toContain('L.Control.Draw');
  });

  it('adds the drawn shape to the FeatureGroup before invoking onCreated', () => {
    // ترتيب حاسم: الإضافة للمجموعة قبل الـcallback كي تقرأه المستهلِكات (القياس/المناطق).
    const addIdx = drawControl.indexOf('featureGroup.addLayer(evt.layer)');
    const cbIdx = drawControl.indexOf('onCreatedRef.current?.(evt)');
    expect(addIdx).toBeGreaterThan(-1);
    expect(cbIdx).toBeGreaterThan(addIdx);
  });
});

describe('MapHub draw/measure vs scout pins — mutual exclusion (click-conflict guard)', () => {
  it('renders both pin-click and measure handlers, so the toggles MUST be exclusive', () => {
    expect(hubMap).toContain('PinClickHandler enabled={pinMode}');
    expect(hubMap).toContain('{drawTools && <MeasureTools />}');
  });

  it('enabling draw/measure disables pins (and compare)', () => {
    // زرّ الرسم/القياس يُعطّل pinMode (وcompare) — وإلّا كلّ نقرة قياس تُسقط دبّوساً.
    expect(mapHub).toMatch(/testid="btn-draw"[\s\S]{0,160}setPinMode\(false\)/);
  });

  it('enabling pins disables draw/measure (and compare)', () => {
    expect(mapHub).toMatch(/testid="btn-pins"[\s\S]{0,160}setDrawTools\(false\)/);
  });
});
