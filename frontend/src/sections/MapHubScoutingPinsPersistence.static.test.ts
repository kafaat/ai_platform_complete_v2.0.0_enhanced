// حارس ساكن: يقفل «دبابيس استكشاف MapHub دائمة تُحفَظ على الخادم» (v94) ويمنع
// الانحدار إلى الحالة المحلّيّة السابقة (جلسة فقط، تضيع عند التحديث). النمط مطابق
// لمرجع SatellitePage: جلب مُخزَّن (useScoutingPins) + إنشاء تفاؤليّ (useCreateScoutingPin)
// مع تراجُع عند الفشل. لا اختراع مشاهدات — الفراغ من القاعدة يبقى فراغاً.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));
const mapHub = readFileSync(join(here, 'MapHub.tsx'), 'utf8');

describe('MapHub: دبابيس الاستكشاف دائمة (تُحفَظ على الخادم)', () => {
  it('يستورد ويستهلك خطّافَي القراءة/الإنشاء من hooks/useScouting', () => {
    expect(mapHub).toContain('useScoutingPins');
    expect(mapHub).toContain('useCreateScoutingPin');
    expect(mapHub).toContain('const scoutingPinsQ = useScoutingPins(fieldId)');
    expect(mapHub).toContain('const createScoutPin = useCreateScoutingPin(fieldId)');
  });

  it('يُنشئ الدبّوس عبر الخادم (mutate) لا الحالة المحلّيّة فقط', () => {
    expect(mapHub).toContain('createScoutPin.mutate');
    // التراجُع عن الدبّوس التفاؤليّ عند فشل الحفظ (صدق: لا يبقى دبّوس وهميّ)
    expect(mapHub).toContain('onError');
  });

  it('يمنع انحدار الحالة المحلّيّة السابقة (session-only pins) والتعليق البائد', () => {
    expect(mapHub).not.toContain('const [pins, setPins] = useState<ScoutPin[]>([])');
    expect(mapHub).not.toContain('بانتظار نقطة قراءة استكشاف خلفيّة');
    expect(mapHub).not.toContain('لا نقطة قراءة scouting خلفيّة');
  });
});
