// T2 (thumb-web): بطاقة اليوم تأخذ المصغّرة والوقت والمنتَج من سجلّ واحد.
//
// الجذر: SatellitePage كان يبني خريطة `تاريخ → thumbnail_url` بـ`Map.set` (الأخير يغلب)
// ثمّ يقرأ `acquisition_datetime` بـ`find` (الأوّل يغلب). مع سجلّين لليوم نفسه تحمل
// البطاقة صورة المشهد B ووقت المشهد A — شاهدان من مشهدين مختلفين على بطاقة واحدة.
import { describe, expect, it } from 'vitest';
import { timelineRecordByDay } from './timelineByDay';

const A = {
  date: '2026-10-20',
  thumbnail_url: 'scene-A.png',
  thumbnail_index: 'truecolor',
  acquisition_datetime: '2026-10-20T10:00:00Z',
  scene_id: 'A',
};
const B = {
  date: '2026-10-20',
  thumbnail_url: 'scene-B.png',
  thumbnail_index: 'ndvi',
  acquisition_datetime: '2026-10-20T08:00:00Z',
  scene_id: 'B',
};

describe('timelineRecordByDay — سجلّ واحد لكلّ يوم', () => {
  it('يومان مكرّران ⇒ المصغّرة والوقت والمنتَج من السجلّ نفسه', () => {
    const rec = timelineRecordByDay([A, B]).get('2026-10-20');
    expect(rec?.scene_id).toBe('A');
    expect(rec?.thumbnail_url).toBe('scene-A.png');
    expect(rec?.acquisition_datetime).toBe('2026-10-20T10:00:00Z');
    expect(rec?.thumbnail_index).toBe('truecolor');
  });

  it('السجلّ الأوّل بلا مصغّرة ⇒ يُختار أوّل سجلّ يحملها كاملاً (لا خلط حقول)', () => {
    const noThumb = { ...A, thumbnail_url: null, scene_id: 'A0' };
    const rec = timelineRecordByDay([noThumb, B]).get('2026-10-20');
    expect(rec?.scene_id).toBe('B');
    expect(rec?.acquisition_datetime).toBe('2026-10-20T08:00:00Z');
  });

  it('لا سجلّ بمصغّرة ⇒ أوّل سجلّ لليوم (الوقت يبقى، والصورة null)', () => {
    const rec = timelineRecordByDay([{ ...A, thumbnail_url: null }]).get('2026-10-20');
    expect(rec?.scene_id).toBe('A');
    expect(rec?.thumbnail_url).toBeNull();
  });

  it('المفتاح يوم YYYY-MM-DD حتّى لو حمل التاريخ ساعة', () => {
    const m = timelineRecordByDay([{ ...A, date: '2026-10-20T00:00:00Z' }]);
    expect(m.get('2026-10-20')?.scene_id).toBe('A');
  });
});
