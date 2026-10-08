import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

// حارسُ هجرة Tailwind v4 في `src/index.css` — ثلاثةُ عقودٍ قِيس كسرُها بفرق البكسل بين بنائي
// v3 وv4 (٩١ مساراً): أيُّ واحدٍ منها إن انكسر عاد الانحرافُ البصريّ صامتاً.

const root = process.cwd();
const css = readFileSync(join(root, 'src/index.css'), 'utf8');

function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...sourceFiles(p));
    else if (/\.(ts|tsx)$/.test(name) && !/\.test\.(ts|tsx)$/.test(name)) out.push(p);
  }
  return out;
}

// يُسقط التعليقات ثمّ يُعيد الكتل العليا: اسمَ القاعدة أو المحدِّد حتّى أوّل `{` أو `;`.
function topLevelPreludes(text: string): string[] {
  const src = text.replace(/\/\*[\s\S]*?\*\//g, '');
  const preludes: string[] = [];
  let depth = 0;
  let start = 0;
  for (let i = 0; i < src.length; i++) {
    const ch = src[i];
    if (ch === '{') {
      if (depth === 0) preludes.push(src.slice(start, i).trim());
      depth++;
    } else if (ch === '}') {
      depth--;
      if (depth === 0) start = i + 1;
    } else if (ch === ';' && depth === 0) {
      preludes.push(src.slice(start, i).trim());
      start = i + 1;
    }
  }
  return preludes.filter(Boolean);
}

const SPACE_Y = /(?:^|[\s'"`])((?:[a-z0-9-]+:)*)(-?space-([xy])-([0-9.]+|px|reverse|\[[^\]]+\]))/g;

function usedSpaceClasses() {
  const found: { file: string; variant: string; axis: string; value: string }[] = [];
  for (const file of sourceFiles(join(root, 'src'))) {
    const text = readFileSync(file, 'utf8');
    for (const m of text.matchAll(SPACE_Y)) {
      found.push({ file: file.slice(root.length + 1), variant: m[1], axis: m[3], value: m[4] });
    }
  }
  return found;
}

describe('Tailwind v4 cascade contract (src/index.css)', () => {
  it('has no unlayered rule: every top-level block is @import/@theme/@layer', () => {
    // قاعدةٌ بلا طبقة تغلب كلَّ أداةٍ في `@layer utilities` مهما كانت خصوصيّتُها — وهكذا محا
    // `* { margin: 0; padding: 0 }` كلَّ `p-*`/`m-*` (٧٥ من ٩١ مساراً تغيّرت).
    const offenders = topLevelPreludes(css).filter((p) => !/^@(import|theme|layer)\b/.test(p));
    expect(offenders).toEqual([]);
  });

  it('keeps the universal reset in @layer base, not utilities', () => {
    // في طبقة الأدوات يساوي `*` أدواتِ `:where()` (space-*/divide-*) خصوصيّةً ويغلبها ترتيباً.
    expect(css).toMatch(/@layer base \{\s*\* \{ box-sizing: border-box; margin: 0; padding: 0; \}\s*\}/);
  });

  it('covers every space-y value used in src/ with a v3 compat rule', () => {
    const covered = new Set(
      [...css.matchAll(/\.space-y-([0-9\\.]+) > :not\(\[hidden\]\) ~ :not\(\[hidden\]\)/g)].map((m) =>
        m[1].replace(/\\/g, ''),
      ),
    );
    const cancelled = new Set(
      [...css.matchAll(/\.space-y-([0-9\\.]+) > :not\(:last-child\)/g)].map((m) => m[1].replace(/\\/g, '')),
    );
    const missing = usedSpaceClasses()
      .filter((u) => u.axis === 'y' && !(covered.has(u.value) && cancelled.has(u.value)))
      .map((u) => `${u.file}: space-y-${u.value}`);
    expect(missing).toEqual([]);
  });

  it('keeps divide-* usage to the pixel-verified allowlist (v4 divide-* has zero specificity)', () => {
    // v4 يرسم فاصلَ `divide-y` حدّاً سفليّاً لكلّ ابنٍ إلّا الأخير بخصوصيّة صفر (`:where`)، وv3 حدّاً
    // علويّاً لكلّ ابنٍ إلّا الأوّل بخصوصيّة (0,3,0). الموضعان الحاليّان في MyFieldsPage أبناؤهما بلا
    // `border-[tby]-*` خاصّ، و`/fields` مطابقٌ بكسلاً لـv3 في السمات الأربع بما فيها عرض الهاتف.
    // موضعٌ جديد يحتاج القياسَ نفسَه قبل إضافته هنا — لا طبقةَ توافقٍ لـdivide-* عمداً (لا حاجةَ مقيسة).
    const uses: string[] = [];
    for (const file of sourceFiles(join(root, 'src'))) {
      const text = readFileSync(file, 'utf8');
      const n = (text.match(/(?:^|[\s'"`])(?:[a-z0-9-]+:)*divide-[xy](?:-[0-9]+|-reverse)?(?=[\s'"`])/g) || []).length;
      if (n) uses.push(`${file.slice(root.length + 1)}×${n}`);
    }
    expect(uses.sort()).toEqual(['src/sections/MyFieldsPage.tsx×2']);
  });

  it('uses no responsive/state space-* variant and no space-x (the compat layer covers neither)', () => {
    // `md:space-y-*` يتطلّب سطرَ توافقٍ داخل الوسيط نفسه، و`space-x-*` في v4 منطقيٌّ (inline)
    // فيتغيّر اتّجاهُه في واجهةٍ RTL — كلاهما قرارٌ صريح لا إضافةٌ صامتة.
    const offenders = usedSpaceClasses()
      .filter((u) => u.variant !== '' || u.axis === 'x')
      .map((u) => `${u.file}: ${u.variant}space-${u.axis}-${u.value}`);
    expect(offenders).toEqual([]);
  });
});
